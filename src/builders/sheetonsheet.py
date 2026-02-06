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
from typing import Dict, Optional, List

from src.core.simulation_base import SimulationBase
from src.core.config import SheetOnSheetSimulationConfig
from src.core.potential_manager import PotentialManager
from src.core.utils import atomic2molecular
from src.builders import components

logger = logging.getLogger(__name__)

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
        stacking_type = getattr(self.config.sheet, 'stack_type', 'AB')
        sheet_path, dims, lat_c = components.build_sheet(
            self.config.sheet, self.atomsk, build_dir,
            stack_if_multi=True, settings=self.config.settings,
            n_layers_override=N_LAYERS, use_pair_bonding=True,
            stacking_type=stacking_type
        )
        self.structure_paths['sheet'] = sheet_path

        self.pm = self._generate_potentials()
        assert lat_c is not None
        for i in range(N_LAYERS):
            self.z_positions[f'layer_{i+1}'] = i * lat_c

        self.lat_c = lat_c
        self.sheet_dims = dims

        self.write_inputs()
        self._generate_hpc_scripts()
        logger.info("Build complete.")

    def _get_hpc_job_name(self) -> str:
        """Get sheet-on-sheet specific job name."""
        return f"sheet_{self.config.sheet.mat}"

    def _collect_simulation_paths(self) -> List[str]:
        """Sheet-on-sheet has single simulation directory."""
        lammps_dir = self.output_dir / 'lammps'
        if lammps_dir.exists():
            return ['.']
        return []

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

        if self.config.settings.simulation.drive_method == 'virtual_atom':
            pm.register_virtual_atom()

        pm.add_self_interaction('sheet')

        pm.add_ghost_lj('sheet', max_real_distance=1)

        settings_path = self.output_dir / "lammps" / "system.in.settings"
        pm.write_file(settings_path)

        for layer in range(N_LAYERS):
            layer_num = layer + 1
            self.groups[f'layer_{layer_num}'] = pm.types.get_layer_group_string(
                'sheet', layer
            )

        self.groups['center'] = ' '.join([self.groups[f'layer_{i}'] for i in range(2, N_LAYERS)])
        self.groups['all_types'] = pm.types.get_group_string('sheet')

        return pm

    def write_inputs(self) -> None:
        """Generates LAMMPS scripts."""
        logger.info("Writing LAMMPS inputs...")

        assert self.pm is not None
        assert self.sheet_dims is not None
        assert self.lat_c is not None

        total_types = len(self.pm.types) if self.pm else 0

        sim = self.config.settings.simulation
        out = self.config.settings.output

        rel_run_dir_str = str(self.relative_run_dir)
        atomic2molecular(f"{self.output_dir}/build/{self.structure_paths['sheet'].name}")

        context = {
            'temp': self.config.general.temp,
            'pressures': self.config.general.pressure,
            'scan_angle_config': self.config.general.scan_angle,
            'scan_speed_config': self.config.general.scan_speed,
            'xlo': self.sheet_dims.get('xlo', 0.0),
            'xhi': self.sheet_dims.get('xhi', 100.0),
            'ylo': self.sheet_dims.get('ylo', 0.0),
            'yhi': self.sheet_dims.get('yhi', 100.0),
            'zhi': self.sheet_dims.get('zhi', 15.0),
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
            'bond_spring_ev': ((self.config.general.bond_spring or 80.0) / 16.02176565  ),
            'bond_min': self.lat_c - 0.15,
            'bond_max': self.lat_c + 0.15,
            'driving_spring_ev': ((self.config.general.driving_spring or 50.0) / 16.02176565),
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
                                    f"friction_p${{pressure}}_a${{a}}_s${{speed}}"),
            'dump_file_pattern': (f"{rel_run_dir_str}/visuals/"
                                    f"slide_p${{pressure}}_a${{a}}_s${{speed}}.lammpstrj"),
            'drive_method': sim.drive_method,
            'thermostat_type': self.config.settings.thermostat.type,
        }

        script = self.render_template("sheetonsheet/slide.lmp", context)
        self.write_file("lammps/slide.in", script)

        logger.info("Inputs written to %s/lammps/", self.output_dir)
