# Settings Reference

\anchor settings_reference

## Overview

FrictionSim2D uses a global `settings.yaml` file for runtime configuration. This file controls:
- Simulation parameters (timestep, run length, minimization)
- Thermostat settings
- Geometry defaults
- HPC cluster configuration
- AiiDA workflow settings

Settings are located at: `src/data/settings/settings.yaml`

## Managing Settings

```bash
# View current settings
FrictionSim2D settings show

# Create default settings file
FrictionSim2D settings init

# Reset to defaults
FrictionSim2D settings reset
```

## Settings Structure

### Simulation Settings

Controls LAMMPS execution parameters:

```yaml
simulation:
  timestep: 0.001              # Integration timestep (ps)
  thermo: 100000               # Thermo output frequency
  min_style: 'cg'              # Minimization algorithm
  minimization_command: 'minimize 1e-4 1e-8 1000000 1000000'
  neighbor_list: 0.3           # Neighbor list skin distance (Angstrom)
  neigh_modify_command: 'neigh_modify every 1 delay 0 check yes'
  slide_run_steps: 500000      # Number of steps in slide.in
  drive_method: 'virtual_atom' # Drive method: 'virtual_atom', 'fix_move', 'smd'
```

**Parameter details**:

- `timestep`: Time integration step in picoseconds
  - Typical: 0.001 ps (1 fs) for most systems
  - Reduce to 0.0005 ps for stiff bonds or high forces

- `thermo`: How often to output thermodynamic data
  - Default: every 100000 steps
  - Set lower for debugging (1000-10000)

- `min_style`: LAMMPS minimization algorithm
  - `cg`: Conjugate gradient (default, stable)
  - `sd`: Steepest descent (simple, slower)
  - `fire`: Fast inertial relaxation (for large systems)

- `slide_run_steps`: Total MD steps in slide.in
  - Default: 500000 (0.5 ns at 0.001 ps timestep)
  - Adjust based on scan speed and desired distance

- `drive_method`: How tip is driven
  - `virtual_atom`: Virtual atom with spring (recommended)
  - `fix_move`: Direct atom motion
  - `smd`: Steered MD

### Thermostat Settings

Configure temperature control:

```yaml
thermostat:
  type: 'langevin'             # Thermostat type
  time_int_type: 'nvt'         # Time integration
  langevin_boundaries:         # Region definitions for Langevin
    tip:
      fix: [3.0, 0.0]          # Fixed region bounds (normalized)
      thermo: [6.0, 3.0]       # Thermostated region bounds
    sub:
      fix: [0.0, 0.3]
      thermo: [0.3, 0.6]
```

**Parameter details**:

- `type`: Thermostat algorithm
  - `langevin`: Stochastic thermostat (default)
  - `nose-hoover`: Deterministic thermostat

- `time_int_type`: Integration scheme
  - `nvt`: Constant N, V, T (with thermostat)
  - `nve`: Constant N, V, E (microcanonical)
  - `verlet`: Velocity-Verlet
  - `respa`: rRESPA multi-timescale

- `langevin_boundaries`: Define which atoms are fixed/thermostated
  - Values are normalized z-positions (0 = bottom, 1 = top)
  - `fix`: Atoms in this range are frozen
  - `thermo`: Atoms in this range are thermostated

### Geometry Settings

Default geometric parameters:

```yaml
geometry:
  tip_reduction_factor: 2.25   # Scale factor for tip size
  rigid_tip: false             # Make tip rigid body
  tip_base_z: 55.0             # Z-position of tip base (Angstrom)
  lat_c_default: 6.0           # Default interlayer spacing (Angstrom)
```

**Parameter details**:

- `tip_reduction_factor`: Scale tip structure by this factor
  - Larger values = smaller tip
  - Used to create realistic tip sizes from bulk structure

- `rigid_tip`: Make tip atoms move as rigid body
  - `true`: Tip doesn't deform (faster, less realistic)
  - `false`: Tip atoms move independently (slower, more realistic)

- `tip_base_z`: Starting Z-position for tip placement
  - Adjusted automatically based on system geometry
  - Manual override for fine control

- `lat_c_default`: Interlayer spacing for 2D materials
  - Used if not specified in config
  - Typical: 6-7 Angstrom for TMDs

### Output Settings

Control dump files and output frequency:

```yaml
output:
  dump:
    system_init: true          # Dump during system.in
    slide: true                # Dump during slide.in
  dump_frequency:
    system_init: 10000         # Dump every N steps in system.in
    slide: 10000               # Dump every N steps in slide.in
  results_frequency: 1000      # Save results every N steps
```

**Parameter details**:

- `dump`: Enable/disable trajectory dumps
  - `true`: Write trajectory files (large!)
  - `false`: Skip dumps (faster, smaller output)

- `dump_frequency`: How often to write frames
  - Lower = more frames, larger files
  - Higher = fewer frames, smaller files
  - Typical: 10000 steps = 10 ps between frames

- `results_frequency`: How often to save results data
  - Results are text files (force, position, etc.)
  - Much smaller than dumps, can be more frequent

### Potential Settings

Interatomic potential configuration:

```yaml
potential:
  LJ_type: 'LJ_base'           # Lennard-Jones potential variant
  LJ_cutoff: 11.0              # LJ cutoff distance (Angstrom)
```

**Parameter details**:

- `LJ_type`: Which LJ mixing rule for cross-interactions
  - `LJ_base`: Standard Lorentz-Berthelot mixing

- `LJ_cutoff`: Cutoff distance for LJ interactions
  - Typical: 10-12 Angstrom
  - Larger = more accurate, slower

### Quench Settings

Parameters for amorphous material generation:

```yaml
quench:
  run_local: true              # Run quench locally or on cluster
  n_procs: 16                  # Number of processors for quench
  quench_slab_dims: [200, 200, 50]  # Quench cell size (Angstrom)
  quench_rate: 1e12            # Cooling rate (K/s)
  quench_melt_temp: 2500       # Melting temperature (K)
  quench_target_temp: 300      # Final temperature (K)
  timestep: 0.002              # Timestep for quench (ps)
  melt_steps: 50000            # Steps at melt temperature
  quench_steps: 100000         # Steps during cooling
  equilibrate_steps: 20000     # Steps at final temperature
```

**Quench process**:
1. Heat to `quench_melt_temp` (melting)
2. Equilibrate for `melt_steps`
3. Cool to `quench_target_temp` at `quench_rate`
4. Equilibrate for `equilibrate_steps`

**Parameter details**:

- `quench_slab_dims`: Size of quenched cell
  - Make large enough to cut required geometry
  - Typical: [200, 200, 50] for most tips/substrates

- `quench_rate`: Cooling rate
  - 1e12 K/s is typical for MD quenches
  - Slower = more relaxed (but more expensive)

- Temperatures: Material-dependent
  - Si: melt_temp ~2500 K
  - SiO2: melt_temp ~3000 K
  - Check material properties

### HPC Settings

Cluster configuration for job submission:

```yaml
hpc:
  # Job submission settings
  scheduler_type: 'pbs'        # 'pbs' or 'slurm'
  queue: null                  # Queue/partition name
  partition: null              # SLURM partition (alternative to queue)
  account: ''                  # Project/account to charge
  hpc_home: 'user@hpc:~/path'  # Remote home (for rsync)
  log_dir: '/path/to/logs'     # HPC log directory
  scratch_dir: '$TMPDIR'       # Scratch directory on compute nodes
  num_nodes: 1                 # Default nodes per job
  num_cpus: 32                 # Default CPUs per node
  memory_gb: 62                # Memory per node (GB)
  walltime_hours: 20           # Default walltime (hours)
  max_array_size: 300          # Maximum array job size
  modules:                     # Modules to load
    - 'tools/prod'
    - 'LAMMPS/29Aug2024-foss-2023b-kokkos'
  mpi_command: 'mpirun'        # MPI launcher
  use_tmpdir: true             # Copy to local scratch
  lammps_scripts:              # Default script order
    - 'system.in'
    - 'slide.in'
```

**Scheduler options**:

PBS example:
```yaml
scheduler_type: 'pbs'
queue: 'normal'
account: 'my_project'
```

SLURM example:
```yaml
scheduler_type: 'slurm'
partition: 'compute'
account: 'my_allocation'
```

**Module loading**: List all required modules in order:

```yaml
modules:
  - 'intel/2023.1'
  - 'impi/2021.9'
  - 'LAMMPS/29Aug2024-intel-kokkos'
```

**Scratch staging**: Use local scratch for I/O performance:

```yaml
use_tmpdir: true
scratch_dir: '$TMPDIR'    # PBS: $TMPDIR, SLURM: /scratch/local/$SLURM_JOB_ID
```

### AiiDA Settings

AiiDA workflow configuration:

```yaml
aiida:
  enabled: false               # Enable AiiDA provenance
  lammps_code_label: 'lammps@my_hpc'      # AiiDA code label
  postprocess_code_label: 'python@my_hpc' # Postprocess code
  postprocess_script_path: '/path/to/read_data.py'
  create_provenance: true      # Create provenance nodes
  auto_import_results: false   # Auto-import results after completion
  hpc_mode: 'offline'          # 'offline', 'local', or 'remote'

  # AiiDA remote computer configuration (optional)
  computer_label: 'localhost'  # AiiDA computer name
  transport: 'local'           # 'local' or 'ssh'
  hostname: null               # Remote hostname (for SSH)
  workdir: null                # Remote work directory
  username: null               # SSH username
  ssh_port: 22                 # SSH port
  key_filename: null           # SSH private key path
```

**HPC modes**:

- `offline`: Generate locally, run manually, import later
- `local`: AiiDA daemon runs on execution machine
- `remote`: AiiDA daemon connects to remote cluster via SSH


## Loading Settings in Python

### Using load_settings()

```python
from src.core.config import load_settings

settings = load_settings()

# Access nested settings
timestep = settings.simulation.timestep
print(f"Timestep: {timestep} ps")

# Modify settings (in memory only)
settings.simulation.slide_run_steps = 1000000
```

### Using Pydantic Models

```python
from src.core.config import GlobalSettings, SimulationSettings

# Create custom settings
custom_settings = GlobalSettings(
    simulation=SimulationSettings(
        timestep=0.0005,
        slide_run_steps=2000000,
    ),
    # ... other sections use defaults
)
```

### Config-Specific Overrides

Override settings per-configuration file:

```ini
# afm_config.ini
[2D]
# ... material config ...

[general]
# ... simulation params ...

[settings_override]
simulation.timestep = 0.0005
simulation.slide_run_steps = 1000000
output.dump_frequency.slide = 5000
```

## Settings Files Location

**Package defaults**:
```
src/data/settings/
├── settings.yaml       # Main settings file
```

**Loading order**:
1. Package default settings (hardcoded in `config.py`)
2. `src/data/settings/settings.yaml` (if exists)
3. Config-specific overrides (if in `.ini` file)

## Common Settings Patterns

### High-Resolution Simulation

```yaml
simulation:
  timestep: 0.0005             # Finer timestep
  slide_run_steps: 2000000     # Longer run

output:
  dump_frequency:
    slide: 5000                # More frequent dumps
  results_frequency: 500
```

### Fast Test Run

```yaml
simulation:
  timestep: 0.001
  slide_run_steps: 50000       # Short run

output:
  dump:
    slide: false               # No dumps
```

### Production HPC Job

```yaml
hpc:
  num_nodes: 4
  num_cpus: 64
  memory_gb: 120
  walltime_hours: 48
  queue: 'long'
  use_tmpdir: true
```

### Multi-Material Study

```yaml
# Use material-specific potential settings
potential:
  LJ_cutoff: 12.0              # Longer cutoff for accuracy

simulation:
  neighbor_list: 0.5           # Larger skin for diverse materials
```

## Environment Variables

Some settings support environment variable interpolation:

```yaml
hpc:
  scratch_dir: '$TMPDIR'       # PBS temporary directory
  log_dir: '$HOME/logs'        # User home directory
```

Available variables depend on the HPC environment:
- PBS: `$TMPDIR`, `$PBS_JOBID`, `$PBS_O_WORKDIR`
- SLURM: `$SLURM_JOB_ID`, `$SLURM_TMPDIR`, `$SLURM_SUBMIT_DIR`

## Validation

Settings are validated when loaded:

```python
from pydantic import ValidationError
from src.core.config import load_settings

try:
    settings = load_settings()
except ValidationError as e:
    print("Settings validation errors:")
    for error in e.errors():
        print(f"  {error['loc']}: {error['msg']}")
```

**Common validation errors**:
- Negative timestep
- Invalid scheduler_type (must be 'pbs' or 'slurm')
- Missing required fields
- Invalid nested structure

## Best Practices

1. **Start from defaults**: Modify only what you need
2. **Test locally**: Verify settings with small test run
3. **Document changes**: Comment why you changed defaults
4. **Version control**: Track settings.yaml in git
5. **Per-project settings**: Copy and customize for each project
6. **Validate early**: Check settings with `FrictionSim2D settings show`
7. **Backup**: Keep copy of working settings before major changes

## See Also

- [Configuration Guide](configuration_guide.md) - Simulation config files
- [AiiDA Workflows](aiida_workflows.md) - AiiDA settings and workflows
- [HPC Two-Phase Jobs](HPC_TWO_PHASE_JOBS.md) - HPC script behavior
- [Commands Reference](commands.md) - Settings management commands
