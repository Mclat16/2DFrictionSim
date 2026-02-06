"""AiiDA plugin for FrictionSim2D.

This module provides optional integration with AiiDA for managing friction simulations.
All functionality gracefully degrades if AiiDA is not installed.

Provides:
- Custom data types (nodes) for storing simulation metadata and results
- Database query interface (Friction2DDB) for accessing stored data  
- Integration functions for registering simulations and importing results

Usage:
------
Registration (done via CLI or programmatically):
    from src.aiida.integration import register_simulation_batch
    register_simulation_batch(simulation_dirs, config_path)

Import results:
    from src.aiida.integration import import_results_to_aiida
    import_results_to_aiida(results_dir)

Query database:
    from src.aiida.db import Friction2DDB
    db = Friction2DDB()
    results = db.query_by_material('h-MoS2')

CLI Commands:
    FrictionSim2D run.afm config.ini --aiida    # Auto-register after building
    FrictionSim2D aiida import ./results        # Import results
    FrictionSim2D aiida query -m h-MoS2         # Query database
"""

try:
    import aiida
    AIIDA_AVAILABLE = True
except ImportError:
    AIIDA_AVAILABLE = False

__all__ = ['AIIDA_AVAILABLE']

if AIIDA_AVAILABLE:
    try:
        # Data nodes
        from .data import (
            FrictionSimulationData,
            FrictionConfigData,
            FrictionResultsData,
            FrictionProvenanceData,
        )
        
        # Database query interface
        from .db import Friction2DDB
        
        # Integration functions (main entry points)
        from .integration import (
            register_simulation_batch,
            register_single_simulation,
            import_results_to_aiida,
        )
        
        __all__.extend([
            # Data nodes
            'FrictionSimulationData',
            'FrictionConfigData',
            'FrictionResultsData',
            'FrictionProvenanceData',
            # Database
            'Friction2DDB',
            # Integration
            'register_simulation_batch',
            'register_single_simulation',
            'import_results_to_aiida',
        ])
    except ImportError as e:
        import warnings
        warnings.warn(
            f"AiiDA is installed but some modules failed to import: {e}",
            ImportWarning
        )
        AIIDA_AVAILABLE = False
