"""Core modules for FrictionSim2D.

This package contains the foundational classes and utilities:
    - Configuration models (Pydantic)
    - Potential management
    - Utility functions for file I/O and calculations
    - Base builder class
"""

from src.core.config import (
    ComponentConfig,
    TipConfig,
    SubstrateConfig,
    SheetConfig,
    GeneralConfig,
    AFMSimulationConfig,
    SheetOnSheetSimulationConfig,
    GlobalSettings,
    load_settings,
    parse_config,
)
from src.core.potential_manager import PotentialManager
from src.core.simulation_base import SimulationBase
from src.core.utils import (
    cifread,
    count_atomtypes,
    lj_params,
    get_material_path,
    get_potential_path,
    read_config,
    get_model_dimensions,
    get_num_atom_types,
    atomic2molecular,
    renumber_atom_types,
    check_potential_cif_compatibility,
)

__all__ = [
    "ComponentConfig",
    "TipConfig",
    "SubstrateConfig",
    "SheetConfig",
    "GeneralConfig",
    "AFMSimulationConfig",
    "SheetOnSheetSimulationConfig",
    "GlobalSettings",
    "load_settings",
    "parse_config",
    "PotentialManager",
    "SimulationBase",
    "cifread",
    "count_atomtypes",
    "lj_params",
    "get_material_path",
    "get_potential_path",
    "read_config",
    "get_model_dimensions",
    "get_num_atom_types",
    "atomic2molecular",
    "renumber_atom_types",
    "check_potential_cif_compatibility",
]
