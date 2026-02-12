"""FrictionSim2D - Framework for 2D material friction simulations.

Provides LAMMPS-based molecular dynamics setup for AFM and sheet-on-sheet
friction simulations with automatic potential generation.
"""

__version__ = "0.2.0"

import logging

from src.core.run import run_simulations
from src.builders.afm import AFMSimulation
from src.builders.sheetonsheet import SheetOnSheetSimulation
from src.core.potential_manager import PotentialManager
from src.core.config import (
    AFMSimulationConfig,
    SheetOnSheetSimulationConfig,
    load_settings,
    parse_config,
)

logger = logging.getLogger(__name__)


def afm(config_file: str = "afm_config.ini", output_root: str = ".",
    generate_hpc: bool = False):
    """Run AFM simulations from config file.

    Args:
        config_file: Path to .ini configuration file.
        output_root: Base directory for the simulation root folder.
    """
    _run_all(config_file, model="afm", output_root=output_root,
             generate_hpc=generate_hpc)


def sheetonsheet(config_file: str = "sheet_config.ini", output_root: str = ".",
                 generate_hpc: bool = False):
    """Run sheet-on-sheet simulations from config file.

    Args:
        config_file: Path to .ini configuration file.
        output_root: Base directory for the simulation root folder.
    """
    _run_all(config_file, model="sheetonsheet", output_root=output_root,
             generate_hpc=generate_hpc)


def _run_all(config_file: str, model: str = "afm", output_root: str = ".",
             generate_hpc: bool = False):
    """Run all simulations defined in config file.

    Args:
        config_file: Path to .ini config file.
        model: Simulation type ('afm' or 'sheetonsheet').
        output_root: Base directory for the simulation root folder.
    """
    created_simulations, simulation_root, configs_to_run, _ = run_simulations(
        config_file=config_file,
        model=model,
        output_root=output_root,
        generate_hpc=generate_hpc,
    )

    print(f"Found {len(configs_to_run)} simulation configurations to run.")
    for idx, sim in enumerate(created_simulations, start=1):
        print(f"  -> Completed [{idx}/{len(created_simulations)}]: {sim}")
    print(f"Simulation root: {simulation_root}")


__all__ = [
    "afm",
    "sheetonsheet",
    "AFMSimulation",
    "SheetOnSheetSimulation",
    "PotentialManager",
    "AFMSimulationConfig",
    "SheetOnSheetSimulationConfig",
    "load_settings",
    "parse_config",
]
