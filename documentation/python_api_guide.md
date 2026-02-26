# Python API Guide

\anchor python_api_guide

## Overview

FrictionSim2D provides a comprehensive Python API for:
- **Programmatic simulation generation**: Build simulations from Python scripts
- **Batch workflows**: Generate and analyze multiple parameter sets
- **AiiDA integration**: Simplified submission with `run_with_aiida()`
- **Custom analysis**: Direct access to simulation builders and data structures

## Quick Start

### Basic Simulation Generation

```python
from src import AFMSimulation, SheetOnSheetSimulation
from src.core.config import parse_config, load_settings

# Load configuration
config = parse_config('afm_config.ini')
settings = load_settings()

# Create simulation
sim = AFMSimulation(config, settings=settings, output_dir='./output')

# Build all components
sim.build()

# Write LAMMPS scripts
sim.write_scripts()

print(f"Simulation created at: {sim.output_dir}")
```

### High-Level Workflow API

```python
from src.core.run import run_simulations

# Generate all simulations from config
simulation_dirs, root_dir = run_simulations(
    config='afm_config.ini',
    model='afm',
    output_root='./simulations',
)

print(f"Created {len(simulation_dirs)} simulations in {root_dir}")
```

### Simplified AiiDA Submission (New!)

```python
from src.aiida.submit import run_with_aiida

# Generate AND submit to AiiDA with one function call
sims, root, nodes = run_with_aiida(
    config_file='afm_config.ini',
    model='afm',
    auto_submit=True,              # Submit automatically (default)
)

print(f"Submitted {len(nodes)} AiiDA jobs")
for node in nodes:
    print(f"  PK={node.pk}: {node.label}")
```

## Core API Components

### Configuration Management

#### parse_config()

Load and validate configuration from various formats:

```python
from src.core.config import parse_config

# From INI file
config = parse_config('config.ini')

# From YAML
config = parse_config('config.yaml')

# From JSON
config = parse_config('config.json')

# From dict
config = parse_config({
    'general': {'temp': 300, 'force': [5, 10, 20]},
    '2D': {'mat': 'MoS2', 'layers': [1, 2]},
    # ...
})

# Returns dict ready for SimulationBase
```

#### load_settings()

Load global settings from package data:

```python
from src.core.config import load_settings

settings = load_settings()

# Access settings
print(settings.simulation.timestep)        # 0.001
print(settings.hpc.scheduler_type)         # 'pbs'
print(settings.output.dump_frequency)      # {'system_init': 10000, 'slide': 10000}

# Modify settings
settings.simulation.slide_run_steps = 1000000
```

#### Pydantic Config Models

Strongly-typed configuration with validation:

```python
from src.core.config import AFMSimulationConfig, GeneralConfig, TipConfig

# Create config programmatically
config = AFMSimulationConfig(
    general=GeneralConfig(
        temp=300,
        force=[5, 10, 20],
        scan_angle=0,
        scan_speed=2,
    ),
    tip=TipConfig(
        mat='Si',
        r=25,
        amorph='c',
        pot_type='sw',
        pot_path='Si.sw',
        cif_path='Si.cif',
    ),
    # ... sub, sheet, settings
)

# Validation happens automatically
try:
    bad_config = TipConfig(r=-5)  # Negative radius
except ValidationError as e:
    print(e)  # "r: ensure this value is greater than 0"
```

### Simulation Builders

#### AFMSimulation

Build AFM (tip-substrate-sheet) simulations:

```python
from src.builders.afm import AFMSimulation

# Initialize
sim = AFMSimulation(
    config=config_dict,
    settings=settings,
    output_dir='./afm_run_001',
    sim_index=1,
)

# Build components step-by-step
sim.setup_directories()
sim.build_2d_sheet()
sim.build_tip()
sim.build_substrate()
sim.combine_system()
sim.write_lammps_scripts()
sim.write_build_provenance()

# OR use convenience method
sim.build()  # Runs all steps above

# Access built data
print(f"System atoms: {sim.system_data['natoms']}")
print(f"Tip group: {sim.groups['tip']}")
print(f"Sheet bounds: {sim.bounds['sheet']}")
```

#### SheetOnSheetSimulation

Build sheet-on-sheet sliding simulations:

```python
from src.builders.sheetonsheet import SheetOnSheetSimulation

sim = SheetOnSheetSimulation(
    config=config_dict,
    settings=settings,
    output_dir='./sheet_run_001',
)

sim.build()

# Access sheet-specific data
print(f"Top sheet group: {sim.groups['top_sheet']}")
print(f"Bottom sheet group: {sim.groups['bottom_sheet']}")
print(f"Bond spring constant: {sim.config_obj.general.bond_spring} eV/A^2")
```

### Workflow Functions

#### run_simulations()

High-level function for batch simulation generation:

```python
from src.core.run import run_simulations

# Basic usage
simulation_dirs, root_dir = run_simulations(
    config='config.ini',
    model='afm',                    # or 'sheetonsheet'
    output_root='./output',
)

# With AiiDA provenance tracking
simulation_dirs, root_dir = run_simulations(
    config='config.ini',
    model='afm',
    use_aiida=True,                 # Enable AiiDA provenance
)

# With HPC script generation
simulation_dirs, root_dir = run_simulations(
    config='config.ini',
    model='afm',
    generate_hpc=True,              # Generate PBS/SLURM scripts
    scheduler='slurm',
)

# Returns
# simulation_dirs: List[Path] - paths to generated simulations
# root_dir: Path - parent directory containing all simulations
```

## AiiDA Integration

### Simplified Interface (Recommended)

The new `run_with_aiida()` function replaces 68 lines of boilerplate with a single call:

```python
from src.aiida.submit import run_with_aiida

# Minimal usage (auto-detect code, use defaults)
sims, root, nodes = run_with_aiida('config.ini', model='afm')

# With manual resource overrides
sims, root, nodes = run_with_aiida(
    'config.ini',
    model='afm',
    machines=4,                    # Override num_machines
    mpiprocs=64,                   # Override procs per machine
    walltime_hours=48,             # Override walltime
    queue='express',               # Override queue
)

# Generate only (no submission)
sims, root, _ = run_with_aiida(
    'config.ini',
    model='afm',
    auto_submit=False,             # Skip submission
)

# Array job submission
sims, root, nodes = run_with_aiida(
    'config.ini',
    model='afm',
    use_array=True,                # Single array job for all sims
)
```

**Parameters**:
- `config_file`: Path to config (.ini, .yaml, .json)
- `model`: 'afm' or 'sheetonsheet'
- `output_root`: Output directory (default: auto-generated timestamp)
- `auto_submit`: Submit to AiiDA immediately (default: True)
- `code_label`: AiiDA code label (default: auto-detect)
- `use_array`: Submit as array job (default: False)
- `**resource_overrides`: Manual resource overrides

**Returns**: `Tuple[List[Path], Path, Optional[List[ProcessNode]]]`
- simulation_dirs: Paths to generated simulations
- root_dir: Parent directory
- nodes: AiiDA process nodes (None if auto_submit=False)

### Manual AiiDA Submission (Advanced)

For fine-grained control:

```python
from pathlib import Path
from aiida import orm, engine
from src.aiida.calcjob import submit_batch
from src.core.config import load_settings

# Load settings and build options
settings = load_settings()
hpc = settings.hpc

options = {
    'resources': {
        'num_machines': hpc.num_nodes,
        'num_mpiprocs_per_machine': hpc.num_cpus,
    },
    'max_wallclock_seconds': hpc.walltime_hours * 3600,
}
if hpc.queue or hpc.partition:
    options['queue_name'] = hpc.queue or hpc.partition
if hpc.account:
    options['account'] = hpc.account
if hpc.modules:
    options['prepend_text'] = '\n'.join(f"module load {m}" for m in hpc.modules)

parameters = {}
if hpc.lammps_scripts:
    parameters['lammps_scripts'] = hpc.lammps_scripts

# Submit simulations
simulation_dirs = list(Path('./output').glob('sim_*'))
code = orm.load_code('lammps@hpc')

processes = submit_batch(
    simulation_dirs=simulation_dirs,
    code_label=code,
    options=options,
    parameters=parameters,
)

print(f"Submitted {len(processes)} CalcJobs")
```

## Advanced Usage

### Custom Material Sweeps

Generate simulations programmatically:

```python
from src.core.config import parse_config
from src.core.run import run_simulations

materials = ['MoS2', 'WSe2', 'graphene', 'h-BN']
forces = [5, 10, 20, 50]

for material in materials:
    # Load base config
    config = parse_config('base_config.ini')

    # Modify for this material
    config['2D']['mat'] = material
    config['2D']['pot_path'] = f'potentials/{material}.sw'
    config['2D']['cif_path'] = f'structures/{material}.cif'

    # Set force sweep
    config['general']['force'] = forces

    # Generate simulations
    sims, root = run_simulations(
        config=config,
        model='afm',
        output_root=f'./output_{material}',
    )

    print(f"{material}: {len(sims)} simulations in {root}")
```

### Conditional Configuration

Build configs with logic:

```python
from src.core.config import AFMSimulationConfig, GeneralConfig

def create_config(material, use_high_res=False):
    """Create config with conditional settings."""

    # Base parameters
    timestep = 0.0005 if use_high_res else 0.001
    run_steps = 2000000 if use_high_res else 500000

    config = AFMSimulationConfig(
        general=GeneralConfig(
            temp=300,
            force=[10, 20] if material == 'soft' else [50, 100],
            scan_speed=1 if use_high_res else 2,
        ),
        # ... tip, sub, sheet configs
        settings=GlobalSettings(
            simulation=SimulationSettings(
                timestep=timestep,
                slide_run_steps=run_steps,
            )
        ),
    )

    return config.model_dump()

# Use in workflow
config = create_config('graphene', use_high_res=True)
sims, root = run_simulations(config=config, model='afm')
```

### Batch Analysis

Analyze results across multiple simulations:

```python
from pathlib import Path
import pandas as pd

def collect_results(simulation_root):
    """Collect results from all simulations."""
    results = []

    for sim_dir in Path(simulation_root).glob('sim_*'):
        # Read simulation metadata
        manifest = json.load(open(sim_dir / 'provenance' / 'manifest.json'))

        # Read results (example)
        result_file = sim_dir / 'results' / 'friction.dat'
        if result_file.exists():
            data = pd.read_csv(result_file, sep='\\s+')

            results.append({
                'simulation': sim_dir.name,
                'material': manifest['parameters']['material'],
                'force': manifest['parameters']['force'],
                'friction': data['friction'].mean(),
                'std': data['friction'].std(),
            })

    return pd.DataFrame(results)

# Analyze
df = collect_results('./simulations/simulation_20250201_120000')
print(df.groupby('material')['friction'].mean())
```

### Custom Potential Manager

Manage non-standard potentials:

```python
from src.core.potential_manager import PotentialManager

pm = PotentialManager()

# Register custom potential
pm.register_potential(
    mat='MyMaterial',
    pot_type='sw',
    pot_path='/path/to/custom.sw',
)

# Use in config
config['2D']['pot_path'] = pm.get_potential_path('MyMaterial', 'sw')
```

## Error Handling

### Configuration Validation

```python
from pydantic import ValidationError
from src.core.config import AFMSimulationConfig, parse_config

try:
    config = parse_config('config.ini')
    validated = AFMSimulationConfig(**config)
except ValidationError as e:
    print("Configuration errors:")
    for error in e.errors():
        print(f"  {error['loc']}: {error['msg']}")
except FileNotFoundError as e:
    print(f"Config file not found: {e}")
```

### Simulation Build Errors

```python
from src.builders.afm import AFMSimulation

try:
    sim = AFMSimulation(config, settings, output_dir='./output')
    sim.build()
except FileNotFoundError as e:
    print(f"Missing file: {e}")
except RuntimeError as e:
    print(f"Build error: {e}")
```

### AiiDA Submission Errors

```python
from src.aiida.submit import run_with_aiida
from aiida.common.exceptions import NotExistent

try:
    sims, root, nodes = run_with_aiida('config.ini', code_label='lammps@hpc')
except NotExistent:
    print("AiiDA code 'lammps@hpc' not found")
    print("Run: FrictionSim2D aiida setup")
except ValueError as e:
    print(f"Configuration error: {e}")
```

## Best Practices

1. **Use Pydantic models**: Leverage validation for robust configs
2. **Handle paths carefully**: Use `Path` objects, check existence
3. **Test locally first**: Generate one simulation before batch runs
4. **Version control**: Track config files and Python scripts together
5. **Document parameters**: Add comments explaining non-obvious choices
6. **Incremental builds**: Build components step-by-step for debugging
7. **Catch exceptions**: Handle file I/O and validation errors gracefully

## Migration from Old API

### Before (68 lines)

```python
from pathlib import Path
from aiida.manage.configuration import load_profile
from aiida.orm import load_code
# ... many more imports ...

load_profile('friction2d')
code = load_code('lammps@hpc')

# ... 50+ lines of setup, directory discovery, dict construction ...

processes = submit_batch(dirs, code, options={'resources': {...}})
```

### After (5 lines)

```python
from src.aiida.submit import run_with_aiida

sims, root, nodes = run_with_aiida(
    'config.ini', model='afm'
)
```

## API Reference

See module docstrings for complete API documentation:
- `src.core.run` - High-level workflow functions
- `src.builders.afm` - AFMSimulation builder
- `src.builders.sheetonsheet` - SheetOnSheetSimulation builder
- `src.core.config` - Configuration models and parsing
- `src.aiida.submit` - AiiDA submission interface
- `src.aiida.calcjob` - CalcJob and Parser definitions

## See Also

- [Configuration Guide](configuration_guide.md) - Config file format
- [AiiDA Workflows](aiida_workflows.md) - Detailed AiiDA usage
- [Examples](examples.md) - Complete working examples
