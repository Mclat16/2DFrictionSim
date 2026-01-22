"""Sheet-on-Sheet Simulation Builder.

This module orchestrates the setup of a friction simulation between two
2D material sheets. The standard model is a 4-layer stack:
    - Layer 1: Fixed (bottom)
    - Layer 2-3: Mobile with Langevin thermostat (friction interface)
    - Layer 4: Rigid, driven by virtual atom (top)

Interlayer interactions:
    - Adjacent layers (1-2, 2-3, 3-4): Real LJ interactions
    - Non-adjacent layers (1-3, 1-4, 2-4): Ghost interactions (prevent interpenetration)
"""

import logging
from pathlib import Path
from typing import Dict, Optional

from src.core.simulation_base import SimulationBase
from src.core.config import SheetOnSheetSimulationConfig
from src.core.potential_manager import PotentialManager
from src.builders import components

logger = logging.getLogger(__name__)

# Standard 4-layer model configuration is hardcoded
N_LAYERS = 4

class SheetOnSheetSimulation(SimulationBase):
    """Builder for Sheet-on-Sheet friction simulations.
    
    Creates a 4-layer stack of the same 2D material:
        - Layer 1: Fixed bottom layer
        - Layer 2: Mobile (Langevin thermostat)
        - Layer 3: Mobile (Langevin thermostat)  
        - Layer 4: Driven top layer (rigid body)
    """

    def __init__(self, config: SheetOnSheetSimulationConfig, output_dir: str,
                    config_path: Optional[str] = None):
        super().__init__(config, output_dir, config_path=config_path)
        self.config: SheetOnSheetSimulationConfig = config
        self.structure_paths: Dict[str, Path] = {}
        self.z_positions: Dict[str, float] = {}
        self.groups: Dict[str, str] = {}
        self.pm: Optional[PotentialManager] = None
        self.lat_c: Optional[float] = None
        self.sheet_dims: Optional[Dict] = None

    def build(self) -> None:
        """Constructs the 4-layer sheet stack."""
        logger.info("Starting Sheet-vs-Sheet Build (4-layer model)...")
        self._create_directories()

        build_dir = self.output_dir / "build"
        build_dir.mkdir(parents=True, exist_ok=True)

        self._init_provenance()

        logger.info("Building %d-layer sheet stack...", N_LAYERS)
        sheet_path, dims, lat_c = components.build_sheet(
            self.config.sheet, self.atomsk, build_dir,
            stack_if_multi=True, settings=self.config.settings,
            n_layers_override=N_LAYERS
        )
        self.structure_paths['sheet'] = sheet_path

        self.pm = self._generate_potentials()

        self.z_positions['layer_1'] = 0.0
        self.z_positions['layer_2'] = lat_c
        self.z_positions['layer_3'] = 2 * lat_c
        self.z_positions['layer_4'] = 3 * lat_c

        self.lat_c = lat_c
        self.sheet_dims = dims

        self.write_inputs()
        logger.info("Build complete.")

    def _init_provenance(self) -> None:
        """Initialize provenance folder and collect input files."""
        prov_dir = self.output_dir / 'provenance'
        prov_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("Provenance folder initialized at: %s", prov_dir)

        self._add_component_files_to_provenance('sheet', self.config.sheet)

        logger.info("Initialized provenance folder: %s", prov_dir)

    def _generate_potentials(self) -> PotentialManager:
        """Configures potential file for 4-layer sheet-on-sheet simulation.
        
        Returns:
            Configured PotentialManager instance.
        """
        pm = PotentialManager(
            self.config.settings,
            potentials_dir=self.output_dir / "provenance" / "potentials",
            potentials_prefix=str(self.relative_run_dir / "provenance" / "potentials")
        )

        pm.register_component('sheet', self.config.sheet, n_layers=N_LAYERS)

        pm.add_self_interaction('sheet')

        pm.add_ghost_lj('sheet', max_real_distance=1)

        settings_path = self.output_dir / "lammps" / "system.in.settings"
        pm.write_file(settings_path)

        for layer in range(N_LAYERS):
            layer_num = layer + 1
            self.groups[f'layer_{layer_num}'] = pm.types.get_layer_group_string(
                'sheet', layer
            )

        self.groups['center'] = f"{self.groups['layer_2']} {self.groups['layer_3']}"
        self.groups['all_types'] = pm.types.get_group_string('sheet')

        return pm

    def write_inputs(self) -> None:
        """Generates LAMMPS scripts."""
        logger.info("Writing LAMMPS inputs...")

        assert self.pm is not None
        assert self.sheet_dims is not None
        assert self.lat_c is not None

        total_types = len(self.pm.types) if self.pm else 0
        virtual_atom_type = total_types + 1

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

        rel_run_dir_str = str(self.relative_run_dir)

        context = {
            'temp': self.config.general.temp,
            'pressures': self.config.general.pressure,
            'angles': self.config.general.scan_angle,
            'scan_speeds': _normalize_speed(self.config.general.scan_speed),
            'xlo': self.sheet_dims.get('xlo', 0.0),
            'xhi': self.sheet_dims.get('xhi', 100.0),
            'ylo': self.sheet_dims.get('ylo', 0.0),
            'yhi': self.sheet_dims.get('yhi', 100.0),
            'data_file': f"{rel_run_dir_str}/build/{self.structure_paths['sheet'].name}",
            'potential_file': f"{rel_run_dir_str}/lammps/system.in.settings",
            'num_atom_types': total_types,
            'ngroups': total_types,
            'layer_1_types': self.groups['layer_1'],
            'layer_2_types': self.groups['layer_2'],
            'layer_3_types': self.groups['layer_3'],
            'layer_4_types': self.groups['layer_4'],
            'center_types': self.groups['center'],
            'n_layers': N_LAYERS,
            'lat_c': self.lat_c,
            'sheet_dims': self.sheet_dims,
            'bond_spring_ev': ((self.config.general.bond_spring or 5.0) /
                                16.02),
            'bond_min': self.lat_c * 0.8,
            'bond_max': self.lat_c * 1.2,
            'driving_spring_ev': ((self.config.general.driving_spring or 50.0) / 16.02),
            'timestep': sim.timestep,
            'thermo': sim.thermo,
            'neighbor_list': sim.neighbor_list,
            'neigh_modify_command': sim.neigh_modify_command,
            'run_steps': sim.slide_run_steps,
            'min_style': sim.min_style,
            'minimization_command': sim.minimization_command,
            'results_freq': out.results_frequency,
            'dump_freq': out.dump_frequency.get('slide', 1000),
            'dump_enabled': out.dump.get('slide', False),
            'results_file_pattern': (f"{rel_run_dir_str}/results/"
                                    f"friction_p${{pressure}}_a${{a}}.dat"),
            'dump_file_pattern': (f"{rel_run_dir_str}/visuals/"
                                    f"slide_p${{pressure}}_a${{a}}.*.dump"),
            'virtual_atom_type': virtual_atom_type,
            'drive_method': sim.drive_method,
            'thermostat_type': self.config.settings.thermostat.type,
        }

        script = self.render_template("sheetonsheet/slide.lmp", context)
        self.write_file("lammps/slide.in", script)

        logger.info("Inputs written to %s/lammps/", self.output_dir)
