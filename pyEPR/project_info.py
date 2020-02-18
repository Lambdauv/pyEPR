"""
Main interface module to use pyEPR.

Contains code to conenct to Ansys and to analyze HFSS files using the EPR method.

This module handles the micowave part of the analysis and conenction to

Further contains code to be able to do autogenerated reports,

Copyright Zlatko Minev, Zaki Leghtas, and the pyEPR team
2015, 2016, 2017, 2018, 2019, 2020
"""

from __future__ import print_function  # Python 2.7 and 3 compatibility

import sys
from pathlib import Path

import pandas as pd

from . import Dict, ansys, config, logger
from .toolbox.pythonic import get_instance_vars


class ProjectInfo(object):
    """
    Primary class to store interface information between ``pyEPR`` and ``Ansys``.

    * **Ansys:** stores and provides easy access to the ansys interface classes :py:class:`pyEPR.ansys.HfssApp`,
      :py:class:`pyEPR.ansys.HfssDesktop`, :py:class:`pyEPR.ansys.HfssProject`, :py:class:`pyEPR.ansys.HfssDesign`,
      :py:class:`pyEPR.ansys.HfssSetup` (which, if present could nbe a subclass, such as a driven modal setup
      :py:class:`pyEPR.ansys.HfssDMSetup`, eigenmode :py:class:`pyEPR.ansys.HfssEMSetup`, or Q3D  :py:class:`pyEPR.ansys.AnsysQ3DSetup`),
      the 3D modeler to design geometry :py:class:`pyEPR.ansys.HfssModeler`.
    * **Junctions:** The class stores params about the design that the user puts will use, such as the names and
      properties of the junctions, such as whihc rectangle and line is associated with which junction.


    Note:

        **Junction parameters.**
        The junction parameters are stored in the ``self.junctions`` ordered dictionary

        A Josephson tunnel junction has to have its parameters specified here for the analysis.
        Each junction is given a name and is specified by a dictionary.
        It has the following properties:

        * ``Lj_variable`` (str):
                Name of HFSS variable that specifies junction inductance Lj defined
                on the boundary condition in HFSS.
                WARNING: DO NOT USE Global names that start with $.
        * ``rect`` (str):
                String of Ansys name of the rectangle on which the lumped boundary condition is defined.
        * ``line`` (str):
                Name of HFSS polyline which spans the length of the recntalge.
                Used to define the voltage across the junction.
                Used to define the current orientation for each junction.
                Used to define sign of ZPF.
        * ``length`` (str):
                Length in HFSS of the junction rectangle and line (specified in meters).
                To create, you can use :code:`epr.parse_units('100um')`.
        * ``Cj_variable`` (str, optional) [experimental]:
                Name of HFSS variable that specifies junction inductance Cj defined
                on the boundary condition in HFSS. DO NOT USE Global names that start with ``$``.

    Warning:

        To define junctions, do **NOT** use global names!
        I.e., do not use names in ansys that start with ``$``.


    Note:

        **Junction parameters example .** To define junction parameters, see the following example

        .. code-block:: python
            :linenos:

            # Create project infor class
            pinfo = ProjectInfo()

            # Now, let us add a junction called `j1`, with the following properties
            pinfo.junctions['j1'] = {
                        'Lj_variable' : 'Lj_1', # name of Lj variable in Ansys
                        'rect'        : 'jj_rect_1',
                        'line'        : 'jj_line_1',
                        'length'      : parse_units('50um'),  # Length is in meters
                        #'Cj'          : 'Cj_1' # name of Cj variable in Ansys - optional
                        }

        To extend to define 5 junctions in bulk, we could use the following script

        .. code-block:: python
            :linenos:

            n_junctions = 5
            for i in range(1, n_junctions + 1):
                pinfo.junctions[f'j{i}'] = {'Lj_variable' : f'Lj_{i}',
                                            'rect'        : f'jj_rect_{i}',
                                            'line'        : f'jj_line_{i}',
                                            'length'      : parse_units('50um')}


    .. _Google Python Style Guide:
        http://google.github.io/styleguide/pyguide.html

    """

    class _Dissipative:
        # TODO: remove and turn to dict

        def __init__(self):
            self.dielectrics_bulk = None
            self.dielectric_surfaces = None
            self.resistive_surfaces = None
            self.seams = None

    def __init__(self, project_path: str = None, project_name: str = None, design_name: str = None,
                 setup_name: str = None, do_connect: bool = True):
        """
        Keyword Arguments:

            project_path (str) : Directory path to the hfss project file.
                Should be the directory, not the file.
                Defaults to ``None``; i.e., assumes the project is open, and thus gets the project based
                on `project_name`.
            project_name (str) : Name of the project within the project_path.
                Defaults to ``None``, which will get the current active one.
            design_name  (str) : Name of the design within the project.
                Defaults to ``None``, which will get the current active one.
            setup_name  (str) :  Name of the setup within the design.
                Defaults to ``None``, which will get the current active one.

            do_connect (bool) [additional]: Do create connection to Ansys or not? Defaults to ``True``.

        """

        # Path: format path correctly to system convention
        self.project_path = str(Path(project_path)) \
            if not (project_path is None) else None
        self.project_name = project_name
        self.design_name = design_name
        self.setup_name = setup_name

        # HFSS desgin: describe junction parameters
        # TODO: introduce modal labels
        self.junctions = Dict()  # See above for help
        self.ports = Dict()

        # Dissipative HFSS volumes and surfaces
        self.dissipative = self._Dissipative()
        self.options = config.ansys

        # Conected to HFSS variable
        self.app = None
        self.desktop = None
        self.project = None
        self.design = None
        self.setup = None

        if do_connect:
            self.connect()

    _Forbidden = ['app', 'design', 'desktop', 'project',
                  'dissipative', 'setup', '_Forbidden', 'junctions']

    def save(self):
        '''
        Return all the data in a dectionary form that can be used to be saved
        '''
        return dict(
            pinfo=pd.Series(get_instance_vars(self, self._Forbidden)),
            dissip=pd.Series(get_instance_vars(self.dissipative)),
            options=pd.Series(get_instance_vars(self.options)),
            junctions=pd.DataFrame(self.junctions),
            ports=pd.DataFrame(self.ports),
        )

    def connect(self):
        """
        Do establihs connection to Ansys desktop.
        """
        logger.info('Connecting to Ansys Desktop API...')

        self.app, self.desktop, self.project = ansys.load_ansys_project(
            self.project_name, self.project_path)
        self.project_name = self.project.name
        self.project_path = self.project.get_path()

        # Design
        if self.design_name is None:
            self.design = self.project.get_active_design()
            self.design_name = self.design.name
            logger.info(f'\tOpened active design\n\
\tDesign:    {self.design_name} [Solution type: {self.design.solution_type}]')
        else:

            try:
                self.design = self.project.get_design(self.design_name)
                logger.info(f'\tOpened active design\n\
\tDesign:    {self.design_name} [Solution type: {self.design.solution_type}]')

            except Exception as e:
                _traceback = sys.exc_info()[2]
                logger.error(f"Original error \N{loudly crying face}: {e}\n")
                raise(Exception(' Did you provide the correct design name?\
                    Failed to pull up design. \N{loudly crying face}').with_traceback(_traceback))

        # Setup
        try:
            setup_names = self.design.get_setup_names()

            if len(setup_names) == 0:
                logger.warning('\tNo design setup detected.')
                if self.design.solution_type == 'Eigenmode':
                    logger.warning('\tCreating eigenmode default setup one.')
                    setup = self.design.create_em_setup()
                    self.setup_name = setup.name
                elif self.design.solution_type == 'DrivenModal':
                    setup = self.design.create_dm_setup()  # adding a driven modal design
                    self.setup_name = setup.name
            else:
                self.setup_name = setup_names[0]

            # get the actual setup if there is one
            self.get_setup(self.setup_name)

        except Exception as e:

            _traceback = sys.exc_info()[2]
            logger.error(f"Original error \N{loudly crying face}: {e}\n")
            raise Exception(' Did you provide the correct setup name?\
                        Failed to pull up setup. \N{loudly crying face}').with_traceback(_traceback)

        # Finalize
        self.project_name = self.project.name
        self.design_name = self.design.name

        logger.info(
            '\tConnection to Ansys established successfully. \N{grinning face} \n')

        return self

    def get_setup(self, name: str):
        """
        Connects to a specific setup for the design.
        Sets  self.setup and self.setup_name.

        Args:
            name (str): Name of the setup.
            If the setup does not exist, then throws a loggger error.
            Defaults to ``None``, in which case returns None

        """
        if name is None:
            return None
        else:
            self.setup = self.design.get_setup(name=self.setup_name)
            if self.setup is None:
                logger.error(f"Could not retrieve setup: {self.setup_name}\n \
                               Did you give the right name? Does it exist?")

            self.setup_name = self.setup.name
            logger.info(
                f'\tOpened setup `{self.setup_name}`  ({type(self.setup)})')
            return self.setup

    def check_connected(self):
        """
        Checks if fully connected including setup.
        """
        return\
            (self.setup is not None) and\
            (self.design is not None) and\
            (self.project is not None) and\
            (self.desktop is not None) and\
            (self.app is not None)

    def disconnect(self):
        '''
        Disconnect from existing HFSS design.
        '''
        assert self.check_connected() is True,\
            "It does not appear that you have connected to HFSS yet.\
            Use the connect()  method. \N{nauseated face}"
        self.project.release()
        self.desktop.release()
        self.app.release()
        ansys.release()

    # UTILITY FUNCTIONS

    def get_dm(self):
        '''
        Utility shortcut function to get the design and modeler.

        .. code-block:: python

            oDesign, oModeler = pinfo.get_dm()

        '''
        return self.design, self.design.modeler

    def get_all_variables_names(self):
        """Returns array of all project and local design names."""
        return self.project.get_variable_names() + self.design.get_variable_names()

    def get_all_object_names(self):
        """Returns array of strings"""
        o_objects = []
        for s in ["Non Model", "Solids", "Unclassified", "Sheets", "Lines"]:
            o_objects += self.design.modeler.get_objects_in_group(s)
        return o_objects

    def validate_junction_info(self):
        """ Validate that the user has put in the junction info correctly.
        Do no also forget to check the length of the rectangles/line of
        the junction if you change it.
        """

        all_variables_names = self.get_all_variables_names()
        all_object_names = self.get_all_object_names()

        for jjnm, jj in self.junctions.items():

            assert jj['Lj_variable'] in all_variables_names,\
                """pyEPR ProjectInfo user error found \N{face with medical mask}:
                Seems like for junction `%s` you specified a design or project
                variable for `Lj_variable` that does not exist in HFSS by the name:
                 `%s` """ % (jjnm, jj['Lj_variable'])

            for name in ['rect', 'line']:

                assert jj[name] in all_object_names, \
                    """pyEPR ProjectInfo user error found \N{face with medical mask}:
                    Seems like for junction `%s` you specified a %s that does not exist
                    in HFSS by the name: `%s` """ % (jjnm, name, jj[name])

        # TODO: Check the length of the rectangle
