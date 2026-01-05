"""AFM Simulation Builder.

This module orchestrates the setup of a complete Atomic Force Microscopy (AFM)
simulation. It coordinates the construction of the Tip, Substrate, and Sheet,
generates the necessary potentials, and writes the LAMMPS input scripts.
"""

import logging
from pathlib import Path
from typing import Dict, Optional

from FrictionSim2D.core.base_builder import BaseBuilder
from FrictionSim2D.core.config import AFMSimulationConfig
from FrictionSim2D.core.potential_manager import PotentialManager
from FrictionSim2D.builders import components

logger = logging.getLogger(__name__)


class AFMSimulation(BaseBuilder):
    """Builder for AFM simulations (Tip + Sheet + Substrate)."""

    def __init__(self, config: AFMSimulationConfig, output_dir: str):
        super().__init__(config, output_dir)
        self.config: AFMSimulationConfig = config  # Type hinting alias

        # State to track build artifacts
        self.structure_paths: Dict[str, Path] = {}
        self.z_positions: Dict[str, float] = {}
        self.groups: Dict[str, str] = {}  # Component name -> Atom type IDs string
        self.pm: Optional[PotentialManager] = None  # Store PM for later use

    def build(self) -> None:
        """Constructs the atomic systems and layout."""
        logger.info("Starting AFM Simulation Build...")
        self._create_directories()
        build_dir = self.output_dir / "build"

        # Determine number of sheet layers
        n_sheet_layers = max(self.config.sheet.layers) if self.config.sheet.layers else 1

        # 1. Build Physical Components
        # Tip
        tip_path, tip_radius = components.build_tip(
            self.config.tip, self.atomsk, build_dir, self.config.settings
        )
        self.structure_paths['tip'] = tip_path

        # Sheet
        sheet_path, sheet_dims, lat_c = components.build_sheet(
            self.config.sheet, self.atomsk, build_dir, 
            stack_if_multi=True, settings=self.config.settings
        )
        self.structure_paths['sheet'] = sheet_path

        # Substrate
        sub_path = components.build_substrate(
            self.config.sub, self.atomsk, build_dir, sheet_dims,
            settings=self.config.settings
        )
        self.structure_paths['sub'] = sub_path

        # 2. Generate Potentials & Calculate Gaps
        self.pm = self._generate_potentials(n_sheet_layers=n_sheet_layers)

        # Calculate Vertical Layout (Z-Offsets)
        gap_sub_sheet = self.pm.calculate_gap('sub', 'sheet', buffer=0.5)
        gap_sheet_tip = self.pm.calculate_gap('sheet', 'tip', buffer=0.5)

        logger.info(f"Calculated gaps: Sub-Sheet={gap_sub_sheet:.2f}A, Sheet-Tip={gap_sheet_tip:.2f}A")

        sub_thickness = self.config.sub.thickness
        
        # Position 1: Substrate (Base)
        self.z_positions['sub'] = 0.0

        # Position 2: Sheet (Above Substrate)
        sheet_base_z = sub_thickness + gap_sub_sheet
        self.z_positions['sheet'] = sheet_base_z

        # Position 3: Tip (Above Sheet)
        sheet_stack_height = (n_sheet_layers - 1) * lat_c

        # Tip Z is usually center of sphere, so add radius
        tip_z = sheet_base_z + sheet_stack_height + gap_sheet_tip + tip_radius
        self.z_positions['tip'] = tip_z

        # Store additional info for templates (calculated values only)
        self.lat_c = lat_c
        self.sheet_dims = sheet_dims

        logger.info("Build complete.")

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
        pm = PotentialManager(self.config.settings)

        # Register components (PM internally knows if Langevin is used)
        pm.register_component('sub', self.config.sub)
        pm.register_component('tip', self.config.tip)
        
        # Sheet with layer-specific types if multiple layers and requires LJ
        sheet_needs_layer_types = (
            n_sheet_layers > 1 and 
            pm.is_sheet_lj(self.config.sheet.pot_type)
        )
        pm.register_component(
            'sheet', 
            self.config.sheet, 
            n_layers=n_sheet_layers if sheet_needs_layer_types else 1
        )

        # Define Self-Interactions (many-body potentials)
        pm.add_self_interaction('sub')
        pm.add_self_interaction('tip')
        pm.add_self_interaction('sheet')

        # Cross Interactions (LJ Mixing between components)
        pm.add_cross_interaction('sub', 'tip')
        pm.add_cross_interaction('sub', 'sheet')
        pm.add_cross_interaction('tip', 'sheet')
        
        # Interlayer interactions for multi-layer sheets
        if sheet_needs_layer_types and n_sheet_layers > 1:
            pm.add_interlayer_interaction('sheet')

        # Write the potential file
        pm.write_file(self.output_dir / "lammps" / "system.in.settings")

        # Store group ID strings for LAMMPS grouping
        self.groups['sub_types'] = pm.get_group_string('sub')
        self.groups['tip_types'] = pm.get_group_string('tip')
        self.groups['sheet_types'] = pm.get_group_string('sheet')
        
        # Store layer-specific groups if applicable
        if sheet_needs_layer_types:
            for layer in range(n_sheet_layers):
                self.groups[f'sheet_l{layer+1}_types'] = pm.get_layer_group_string('sheet', layer)

        return pm

    def write_inputs(self) -> None:
        """Generates the LAMMPS input scripts."""
        logger.info("Writing LAMMPS inputs...")

        # Get total types from PotentialManager
        total_types = self.pm.get_total_types() if self.pm else len(set(
            t for s in self.groups.values() for t in s.split()
        ))

        context = {
            'temp': self.config.general.temp,
            'force': self.config.general.force,
            'angle': self.config.general.scan_angle,
            'speed': self.config.tip.s,
            'settings': self.config.settings.simulation,

            'path_sub': f"../build/{self.structure_paths['sub'].name}",
            'path_tip': f"../build/{self.structure_paths['tip'].name}",
            'path_sheet': f"../build/{self.structure_paths['sheet'].name}",

            'z_sub': self.z_positions['sub'],
            'z_sheet': self.z_positions['sheet'],
            'z_tip': self.z_positions['tip'],

            'sub_types': self.groups['sub_types'],
            'tip_types': self.groups['tip_types'],
            'sheet_types': self.groups['sheet_types'],
            'ngroups': total_types,

            'sub_natypes': len(self.groups['sub_types'].split()),
            'tip_natypes': len(self.groups['tip_types'].split()),

            'damp_ev': self.config.tip.dspring / 0.016,
            'spring_ev': (self.config.general.driving_spring or 8.0) / 16.02,  # N/m to eV/Å²
            'tipps': self.config.tip.s / 100,
            'drive_method': self.config.settings.simulation.drive_method,
            'virtual_offset': 10.0, 
            'virtual_atom_type': total_types + 1,
            'run_steps': self.config.settings.simulation.slide_run_steps,
            'results_freq': self.config.settings.output.results_frequency,
            'dump_freq': self.config.settings.output.dump_frequency['slide'],
            
            # Multi-layer sheet context
            'n_sheet_layers': max(self.config.sheet.layers) if self.config.sheet.layers else 1,
            'lat_c': self.lat_c,  # Calculated during build
            'tip_radius': self.config.tip.r,  # From config
            'sheet_dims': self.sheet_dims,  # Actual dimensions from build
            
            # Thermostat settings
            'thermostat_type': self.config.settings.thermostat.type,
            'use_langevin': self.config.settings.thermostat.type == 'langevin',
        }

        init_script = self.render_template("afm/system_init.lmp", context)
        self.write_file("lammps/system.in", init_script)

        slide_script = self.render_template("afm/slide.lmp", context)
        self.write_file("lammps/slide.in", slide_script)

        logger.info(f"Inputs written to {self.output_dir}/lammps/")