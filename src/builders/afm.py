"""AFM Simulation Builder.

This module orchestrates the setup of a complete Atomic Force Microscopy (AFM)
simulation. It coordinates the construction of the Tip, Substrate, and Sheet,
generates the necessary potentials, and writes the LAMMPS input scripts.
"""

import logging
import shutil
from pathlib import Path
from typing import Dict, Optional

from src.core.simulation_base import SimulationBase
from src.core.config import AFMSimulationConfig
from src.core.potential_manager import PotentialManager
from src.builders import components

logger = logging.getLogger(__name__)


class AFMSimulation(SimulationBase):
    """Builder for AFM simulations (Tip + Sheet + Substrate).
    
    Handles layer sweeps internally - when config.sheet.layers is a list,
    builds common components once and iterates over layer counts.
    """

    def __init__(self, config: AFMSimulationConfig, output_dir: str,
                    config_path: Optional[str] = None):
        super().__init__(config, output_dir, config_path=config_path)
        self.config: AFMSimulationConfig = config

        self.base_output_dir = self.output_dir
        self.base_relative_run_dir = self.relative_run_dir

        self.structure_paths: Dict[str, Path] = {}
        self.z_positions: Dict[str, float] = {}
        self.groups: Dict[str, str] = {}
        self.pm: Optional[PotentialManager] = None

        self._tip_path: Optional[Path] = None
        self._tip_radius: Optional[float] = None
        self._sub_path: Optional[Path] = None
        self._monolayer_path: Optional[Path] = None
        self._monolayer_dims: Optional[dict] = None
        self._base_lat_c: Optional[float] = None
        self._pot_counts: Optional[dict] = None
        self._total_pot_types: Optional[int] = None

        self.lat_c: Optional[float] = None
        self.sheet_dims: Optional[dict] = None

    def build(self) -> None:
        """Constructs the atomic systems and layout.
        
        If config.sheet.layers is a list, iterates over layer counts.
        """
        logger.info("Starting AFM Simulation Build...")

        layers = self.config.sheet.layers
        if isinstance(layers, int):
            layers = [layers]
        elif not layers:
            layers = [1]

        self._init_provenance()

        shared_build_dir = self.base_output_dir / "build"
        if shared_build_dir.exists():
            shutil.rmtree(shared_build_dir)
        shared_build_dir.mkdir(parents=True, exist_ok=True)

        self._build_common_components(shared_build_dir)

        for n_layers in layers:
            logger.info("--- Building for %s layer(s) ---", n_layers)

            self.output_dir = self.base_output_dir / f"L{n_layers}"
            self.relative_run_dir = self.base_relative_run_dir / f"L{n_layers}"

            self._create_directories()
            self._stack_sheets(n_layers, shared_build_dir)

            assert self._tip_path is not None
            assert self._sub_path is not None
            self.structure_paths['tip'] = shared_build_dir / self._tip_path.name
            self.structure_paths['sub'] = shared_build_dir / self._sub_path.name

            self.pm = self._generate_potentials(n_sheet_layers=n_layers)
            self._calculate_z_positions(n_layers)
            self.write_inputs()

        logger.info("Build complete for all layer configurations.")

    def _init_provenance(self) -> None:
        """Initialize provenance folder and collect input files."""
        prov_dir = self.base_output_dir / 'provenance'
        prov_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("Provenance folder initialized at: %s", prov_dir)

        for component_name, config in [
            ('sheet', self.config.sheet),
            ('tip', self.config.tip),
            ('sub', self.config.sub)
        ]:
            self._add_component_files_to_provenance(component_name, config)

        logger.info("Initialized provenance folder: %s", prov_dir)

    def _build_common_components(self, build_dir: Path) -> None:
        """Builds tip, substrate, and monolayer (components shared across layers)."""
        self._tip_path, self._tip_radius = components.build_tip(
            self.config.tip, self.atomsk, build_dir, self.config.settings
        )
        logger.info("Built tip: %s", self._tip_path.name)

        (self._monolayer_path, self._monolayer_dims,
            self._base_lat_c, self._pot_counts, self._total_pot_types) = (
            components.build_monolayer(
                self.config.sheet, self.atomsk, build_dir, self.config.settings
            )
        )
        logger.info("Built monolayer: %s", self._monolayer_path.name)

        self._sub_path = components.build_substrate(
            self.config.sub, self.atomsk, build_dir, self._monolayer_dims,
            settings=self.config.settings
        )
        logger.info("Built substrate: %s", self._sub_path.name)

    def _stack_sheets(self, n_layers: int, build_dir: Path) -> None:
        """Stacks the monolayer to create n-layer sheet."""
        assert self._monolayer_path is not None
        assert self._monolayer_dims is not None
        assert self._base_lat_c is not None

        if n_layers == 1:
            sheet_path = build_dir / f"{self.config.sheet.mat}_1.lmp"
            if sheet_path != self._monolayer_path:
                shutil.copy(self._monolayer_path, sheet_path)
            self.structure_paths['sheet'] = sheet_path
            self.lat_c = self._base_lat_c
            self.sheet_dims = self._monolayer_dims
        else:
            assert self._total_pot_types is not None
            assert self._pot_counts is not None
            stacked_path = build_dir / f"{self.config.sheet.mat}_{n_layers}.lmp"
            stacked_path, lat_c = components.stack_multilayer_sheet(
                base_layer_path=self._monolayer_path,
                config=self.config.sheet,
                output_path=stacked_path,
                box_dims=self._monolayer_dims,
                n_layers=n_layers,
                types_per_layer=self._total_pot_types,
                pot_counts=self._pot_counts,
                lat_c=self._base_lat_c,
                settings=self.config.settings
            )
            self.structure_paths['sheet'] = stacked_path
            self.lat_c = lat_c
            self.sheet_dims = self._monolayer_dims

    def _calculate_z_positions(self, n_layers: int) -> None:
        """Calculates vertical positions for all components."""
        assert self.pm is not None
        assert self.lat_c is not None
        assert self._tip_radius is not None

        gap_sub_sheet = self.pm.calculate_gap('sub', 'sheet', buffer=0.5)
        gap_sheet_tip = self.pm.calculate_gap('sheet', 'tip', buffer=0.5)

        logger.info("Calculated gaps: Sub-Sheet=%.2fA, Sheet-Tip=%.2fA",
                    gap_sub_sheet, gap_sheet_tip)

        sub_thickness = self.config.sub.thickness

        self.z_positions['sub'] = 0.0
        sheet_base_z = sub_thickness + gap_sub_sheet
        self.z_positions['sheet'] = sheet_base_z

        sheet_stack_height = (n_layers - 1) * self.lat_c
        tip_z = (sheet_base_z + sheet_stack_height + gap_sheet_tip +
                    self._tip_radius)
        self.z_positions['tip'] = tip_z

    def _generate_potentials(
        self,
        n_sheet_layers: int = 1
    ) -> PotentialManager:
        """Configures and writes the potential file using PotentialManager.
        
        Args:
            n_sheet_layers: Number of 2D material layers.
            
        Returns:
            Configured PotentialManager instance.
        """
        pm = PotentialManager(
            self.config.settings,
            potentials_dir=self.base_output_dir / "provenance" / "potentials",
            potentials_prefix=str(self.base_relative_run_dir / "provenance" / "potentials"),
        )

        pm.register_component('sub', self.config.sub)
        pm.register_component('tip', self.config.tip)

        sheet_needs_layer_types = (
            n_sheet_layers > 1 and
            pm.is_sheet_lj(self.config.sheet.pot_type)
        )
        pm.register_component(
            'sheet',
            self.config.sheet,
            n_layers=n_sheet_layers if sheet_needs_layer_types else 1
        )

        pm.add_self_interaction('sub')
        pm.add_self_interaction('tip')
        pm.add_self_interaction('sheet')

        pm.add_cross_interaction('sub', 'tip')
        pm.add_cross_interaction('sub', 'sheet')
        pm.add_cross_interaction('tip', 'sheet')

        if sheet_needs_layer_types and n_sheet_layers > 1:
            pm.add_interlayer_interaction('sheet')

        settings_path = self.output_dir / "lammps" / "system.in.settings"
        pm.write_file(settings_path)

        self.groups['sub_types'] = pm.types.get_group_string('sub')
        self.groups['tip_types'] = pm.types.get_group_string('tip')
        self.groups['sheet_types'] = pm.types.get_group_string('sheet')

        if sheet_needs_layer_types:
            for layer in range(n_sheet_layers):
                layer_key = f'sheet_l{layer+1}_types'
                self.groups[layer_key] = pm.types.get_layer_group_string('sheet', layer)

        return pm

    def write_inputs(self) -> None:
        """Generates the LAMMPS input scripts."""
        logger.info("Writing LAMMPS inputs...")

        assert self.pm is not None
        assert self.sheet_dims is not None

        total_types = len(self.pm.types) if self.pm else len(set(
            t for s in self.groups.values() for t in s.split()
        ))

        sim = self.config.settings.simulation
        out = self.config.settings.output

        def _normalize_speed(speed):
            if speed is None:
                return 0.0
            if isinstance(speed, (int, float)):
                return speed / 100
            if isinstance(speed, list):
                return [s / 100 for s in speed]
            raise TypeError(f"Unsupported scan_speed type: {type(speed)}")

        if self.config.general.scan_speed is None:
            raise ValueError("scan_speed must be specified in [general] section")
        scan_speeds = _normalize_speed(self.config.general.scan_speed)

        xlo, xhi = self.sheet_dims['xlo'], self.sheet_dims['xhi']
        ylo, yhi = self.sheet_dims['ylo'], self.sheet_dims['yhi']
        zhi_box = self.z_positions['tip'] + 50.0

        tip_x = (xlo + xhi) / 2.0
        tip_y = (ylo + yhi) / 2.0
        tip_z = self.z_positions['tip']

        sub_natypes = len(self.groups['sub_types'].split())
        tip_natypes = len(self.groups['tip_types'].split())
        offset_2d = sub_natypes + tip_natypes

        rel_run_dir_str = str(self.relative_run_dir)
        rel_base_dir_str = str(self.base_relative_run_dir)

        context = {
            'temp': self.config.general.temp,
            'forces': self.config.general.force,
            'angles': self.config.general.scan_angle,
            'scan_speeds': scan_speeds,
            'xlo': xlo,
            'xhi': xhi,
            'ylo': ylo,
            'yhi': yhi,
            'zhi_box': zhi_box,
            'data_file': f"{rel_base_dir_str}/build/{self.structure_paths['sheet'].name}",
            'potential_file': f"{rel_run_dir_str}/lammps/system.in.settings",
            'sub_file': f"{rel_base_dir_str}/build/{self.structure_paths['sub'].name}",
            'tip_file': f"{rel_base_dir_str}/build/{self.structure_paths['tip'].name}",
            'sheet_file': f"{rel_base_dir_str}/build/{self.structure_paths['sheet'].name}",
            'path_sub': f"{rel_base_dir_str}/build/{self.structure_paths['sub'].name}",
            'path_tip': f"{rel_base_dir_str}/build/{self.structure_paths['tip'].name}",
            'path_sheet': f"{rel_base_dir_str}/build/{self.structure_paths['sheet'].name}",
            'tip_x': tip_x,
            'tip_y': tip_y,
            'tip_z': tip_z,
            'sheet_z': self.z_positions['sheet'],
            'offset_2d': offset_2d,
            'results_file_pattern': (f"{rel_run_dir_str}/results/"
                                    f"friction_f${{find}}_a${{a}}.dat"),
            'dump_file_pattern': (f"{rel_run_dir_str}/visuals/"
                                    f"slide_f${{find}}_a${{a}}.*.dump"),
            'dump_enabled': out.dump.get('slide', False),
            'z_sub': self.z_positions['sub'],
            'z_sheet': self.z_positions['sheet'],
            'z_tip': self.z_positions['tip'],
            'sub_types': self.groups['sub_types'],
            'tip_types': self.groups['tip_types'],
            'sheet_types': self.groups['sheet_types'],
            'ngroups': total_types,
            'extra_atom_types': 1,
            'sub_natypes': sub_natypes,
            'tip_natypes': tip_natypes,
            'timestep': sim.timestep,
            'thermo': sim.thermo,
            'neighbor_list': sim.neighbor_list,
            'neigh_modify_command': sim.neigh_modify_command,
            'run_steps': sim.slide_run_steps,
            'drive_method': sim.drive_method,
            'damp_ev': self.config.tip.dspring / 0.016,
            'spring_ev': (self.config.general.driving_spring or 8.0) / 16.02,
            'virtual_offset': 10.0, 
            'virtual_atom_type': total_types + 1,
            'results_freq': out.results_frequency,
            'dump_freq': out.dump_frequency.get('slide', 1000),
            'tip_fix_group': 'tip',
            'layer_group': 'sheet',
            'n_sheet_layers': (max(self.config.sheet.layers)
                                if self.config.sheet.layers else 1),
            'lat_c': self.lat_c,
            'tip_radius': self.config.tip.r,
            'sheet_dims': self.sheet_dims,
            'thermostat_type': self.config.settings.thermostat.type,
            'use_langevin': self.config.settings.thermostat.type == 'langevin',
            'min_style': sim.min_style,
            'minimization_command': sim.minimization_command,
            'output_dir': f"{rel_run_dir_str}/results",
            'dump_file': f"{rel_run_dir_str}/visuals/system.*.dump",
        }

        init_script = self.render_template("afm/system_init.lmp", context)
        self.write_file("lammps/system.in", init_script)

        slide_script = self.render_template("afm/slide.lmp", context)
        self.write_file("lammps/slide.in", slide_script)

        logger.info("Inputs written to %s/lammps/", self.output_dir)
