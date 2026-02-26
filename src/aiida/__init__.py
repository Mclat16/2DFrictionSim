"""AiiDA integration for FrictionSim2D.

This package intentionally keeps a thin root module and lazy-loads
advanced symbols to reduce import-time coupling across AiiDA plugins.
"""

from importlib import import_module
from typing import Any, Dict, Tuple

try:
    import aiida  # noqa: F401
    AIIDA_AVAILABLE = True
except ImportError:
    AIIDA_AVAILABLE = False

if AIIDA_AVAILABLE:
    from aiida.manage.configuration import load_profile as LOAD_PROFILE
else:
    LOAD_PROFILE = None

_LAZY_EXPORTS: Dict[str, Tuple[str, str]] = {
    'FrictionSimulationData': ('src.aiida.data', 'FrictionSimulationData'),
    'FrictionResultsData': ('src.aiida.data', 'FrictionResultsData'),
    'FrictionProvenanceData': ('src.aiida.data', 'FrictionProvenanceData'),
    'Friction2DDB': ('src.aiida.query', 'Friction2DDB'),
    'register_simulation_batch': ('src.aiida.integration', 'register_simulation_batch'),
    'register_single_simulation': ('src.aiida.integration', 'register_single_simulation'),
    'import_results_to_aiida': ('src.aiida.integration', 'import_results_to_aiida'),
    'export_archive': ('src.aiida.integration', 'export_archive'),
    'import_archive': ('src.aiida.integration', 'import_archive'),
    'LammpsFrictionCalcJob': ('src.aiida.calcjob', 'LammpsFrictionCalcJob'),
    'FrictionWorkChain': ('src.aiida.workchain', 'FrictionWorkChain'),
    'run_with_aiida': ('src.aiida.submit', 'run_with_aiida'),
    'smart_submit': ('src.aiida.submit', 'smart_submit'),
    'full_setup': ('src.aiida.setup', 'full_setup'),
}

__all__ = ['AIIDA_AVAILABLE', 'load_aiida_profile']


def load_aiida_profile(profile_name=None):
    """Load an AiiDA profile, required before using any AiiDA functionality.

    Should be called once at application startup (e.g. from the CLI) before
    any AiiDA nodes are created or queried.

    Args:
        profile_name: Name of the AiiDA profile to load. If ``None``,
            the default profile is loaded.

    Returns:
        The loaded ``aiida.manage.configuration.Profile`` instance.

    Raises:
        RuntimeError: If AiiDA is not installed.
        aiida.common.exceptions.ProfileConfigurationError: If profile not found.
    """
    if not AIIDA_AVAILABLE:
        raise RuntimeError(
            "AiiDA is not installed. Install with: pip install 'FrictionSim2D[aiida]'"
        )
    if LOAD_PROFILE is None:
        raise RuntimeError("AiiDA profile loader is unavailable")
    return LOAD_PROFILE(profile_name)


def __getattr__(name: str) -> Any:
    """Lazy-load optional AiiDA symbols exported at package root."""
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module 'src.aiida' has no attribute '{name}'")
    if not AIIDA_AVAILABLE:
        raise AttributeError(
            f"AiiDA is unavailable; cannot access '{name}'. "
            "Install with: pip install 'FrictionSim2D[aiida]'"
        )

    module_name, symbol_name = _LAZY_EXPORTS[name]
    module = import_module(module_name)
    value = getattr(module, symbol_name)
    globals()[name] = value
    return value
