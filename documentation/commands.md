# Commands Reference

\anchor commands

Complete CLI command reference for FrictionSim2D.

## Main Entrypoint

```bash
FrictionSim2D --help        # Show all commands
FrictionSim2D --version     # Show version
```

---

## run - Generate Simulations

### run afm

Generate AFM (tip-substrate-sheet) simulations.

```bash
FrictionSim2D run afm CONFIG_FILE [OPTIONS]
```

**Arguments**:
- `CONFIG_FILE`: Path to `.ini` configuration file

**Options**:
- `--output-dir DIR`: Output directory (default: auto-generated timestamp)
- `--aiida`: Enable AiiDA provenance tracking
- `--hpc-scripts`: Generate HPC submission scripts (PBS/SLURM)
- `--hpc NAME`: Specify HPC template name
- `--local`: Run locally (default behavior)

**Examples**:

```bash
# Basic generation
FrictionSim2D run afm afm_config.ini

# With custom output directory
FrictionSim2D run afm config.ini --output-dir ./my_simulations

# With AiiDA provenance
FrictionSim2D run afm config.ini --aiida

# With HPC scripts
FrictionSim2D run afm config.ini --hpc-scripts

# Combined: AiiDA + HPC scripts
FrictionSim2D run afm config.ini --aiida --hpc-scripts
```

### run sheetonsheet

Generate sheet-on-sheet sliding simulations.

```bash
FrictionSim2D run sheetonsheet CONFIG_FILE [OPTIONS]
```

**Arguments**:
- `CONFIG_FILE`: Path to `.ini` configuration file

**Options**: Same as `run afm`

**Examples**:

```bash
# Basic generation
FrictionSim2D run sheetonsheet sheet_config.ini

# With AiiDA and HPC scripts
FrictionSim2D run sheetonsheet config.ini --aiida --hpc-scripts
```

---

## hpc - HPC Script Management

### hpc generate

Generate PBS/SLURM submission scripts for existing simulations.

```bash
FrictionSim2D hpc generate SIMULATION_DIR [OPTIONS]
```

**Arguments**:
- `SIMULATION_DIR`: Path to simulation root directory

**Options**:
- `--scheduler {pbs,slurm}`: Scheduler type (default: from settings.yaml)
- `--output-dir DIR`: Override output location for HPC scripts

**Examples**:

```bash
# Generate PBS scripts
FrictionSim2D hpc generate ./output/simulation_20250201_120000

# Generate SLURM scripts
FrictionSim2D hpc generate ./output/simulation_20250201_120000 --scheduler slurm

# Custom output location
FrictionSim2D hpc generate ./simulations --output-dir ./hpc_scripts
```

**Generated files**:
- AFM simulations: `run_system.pbs`, `run_slide.pbs`, `submit_jobs.sh`, manifests
- Sheet-on-sheet: `run.pbs` or `run.sh`, manifest

---

## settings - Settings Management

### settings show

Display current global settings.

```bash
FrictionSim2D settings show
```

Shows all settings from `src/data/settings/settings.yaml` including:
- Simulation parameters
- HPC configuration
- AiiDA settings

### settings init

Create default settings file if missing.

```bash
FrictionSim2D settings init
```

Creates `src/data/settings/settings.yaml` with default values.

### settings reset

Reset settings to package defaults.

```bash
FrictionSim2D settings reset
```

**Warning**: This overwrites your settings file. Backup first if you have customizations.

---

## aiida - AiiDA Workflow Commands

### aiida setup

Initialize AiiDA environment (one-time setup).

```bash
FrictionSim2D aiida setup [OPTIONS]
```

**Options**:
- `--profile NAME`: AiiDA profile name (default: 'friction2d')
- `--lammps-path PATH`: Path to LAMMPS executable (default: auto-detect)
- `--use-remote`: Configure remote HPC computer from settings.yaml

**What it does**:
1. Starts RabbitMQ broker
2. Creates AiiDA profile with PostgreSQL
3. Configures localhost computer
4. Sets up LAMMPS code

**Examples**:

```bash
# Basic setup
FrictionSim2D aiida setup

# Custom profile name
FrictionSim2D aiida setup --profile my_profile

# Custom LAMMPS path
FrictionSim2D aiida setup --lammps-path /opt/lammps/bin/lmp

# Setup remote HPC computer
FrictionSim2D aiida setup --use-remote
```

### aiida status

Check AiiDA daemon and recent job status.

```bash
FrictionSim2D aiida status
```

**Output**:
```
Daemon: Running
Profile: friction2d
Recent calculations:
  PK=1234  afm_MoS2_1L_5nN      State: running
  PK=1235  afm_MoS2_2L_10nN     State: finished
  PK=1236  afm_MoS2_3L_20nN     State: failed
```

### aiida submit

Submit simulations to AiiDA with smart defaults and prompting.

```bash
FrictionSim2D aiida submit SIMULATION_DIR [OPTIONS]
```

**New Simplified Interface** (v0.2.0):

**Arguments**:
- `SIMULATION_DIR`: Path to simulation root or individual simulation

**Options**:
- `-c, --code LABEL`: AiiDA code label (default: auto-detect)
- `--scripts CSV`: Comma-separated LAMMPS scripts to run
- `--array`: Submit as single array job

**Resource overrides** (optional):
- `--machines N`: Number of nodes
- `--mpiprocs N`: MPI processes per node
- `--walltime TIME`: Walltime (HH:MM:SS or hours)
- `--queue NAME`: Queue/partition name
- `--project NAME`: Account/project to charge

**Other options**:
- `--dry-run`: Preview configuration without submitting

**Examples**:

```bash
# Minimal (auto-detect code, use defaults)
FrictionSim2D aiida submit ./output

# With manual overrides
FrictionSim2D aiida submit ./output --machines 4 --walltime 24:00:00

# Preview before submitting
FrictionSim2D aiida submit ./output --dry-run

# Array job
FrictionSim2D aiida submit ./output --array

# Specify code
FrictionSim2D aiida submit ./output --code lammps@hpc

# Custom scripts
FrictionSim2D aiida submit ./output --scripts system.in,slide_1.in,slide_2.in

# Full control
FrictionSim2D aiida submit ./output \\
  --code lammps@hpc \\
  --machines 8 \\
  --walltime 72:00:00 \\
  --queue express \\
  --project my_allocation
```

**Interactive prompting**: If code not specified and multiple codes exist:

```
Available LAMMPS codes:
  1. lammps@localhost
  2. lammps@hpc
Select code [1]: 2

Using defaults from settings.yaml (1 node, 32 CPUs/node, 20h walltime)

Preview:
  Code: lammps@hpc
  Simulations: 15
  Resources: 1 nodes, 32 CPUs/node, 20h

Proceed with submission? [Y/n]:
```

### aiida import

Import completed simulation results into AiiDA.

```bash
FrictionSim2D aiida import RESULTS_DIR [OPTIONS]
```

**Arguments**:
- `RESULTS_DIR`: Path to directory with completed results

**Options**:
- `--process` / `--no-process`: Run post-processing (default: yes)

**Examples**:

```bash
# Import results with post-processing
FrictionSim2D aiida import ./returned_results

# Import without post-processing
FrictionSim2D aiida import ./results --no-process
```

### aiida query

Query AiiDA database for simulation results.

```bash
FrictionSim2D aiida query [OPTIONS]
```

**Filter options**:
- `--material MAT`: Filter by material
- `--layers N`: Filter by layer count
- `--force F`: Filter by force value
- `--pressure P`: Filter by pressure value
- `--temperature T`: Filter by temperature

**Output options**:
- `--format {table,csv,json}`: Output format (default: table)
- `--output FILE`: Save to file

**Examples**:

```bash
# Query all simulations
FrictionSim2D aiida query

# Filter by material
FrictionSim2D aiida query --material MoS2

# Multiple filters
FrictionSim2D aiida query --material MoS2 --layers 2 --force 10

# CSV output
FrictionSim2D aiida query --material MoS2 --format csv

# Save to file
FrictionSim2D aiida query --output results.csv

# JSON for scripting
FrictionSim2D aiida query --format json --output results.json
```

### aiida export

Export AiiDA archive for transfer/backup.

```bash
FrictionSim2D aiida export [OPTIONS]
```

**Options**:
- `--output FILE`: Archive filename (default: friction_archive.aiida)
- `--material MAT`: Filter by material (export only matching)
- `--layers N`: Filter by layers
- `--force F`: Filter by force

**Examples**:

```bash
# Export everything
FrictionSim2D aiida export --output all_data.aiida

# Export filtered data
FrictionSim2D aiida export --material MoS2 --output mos2_only.aiida

# Export specific layers
FrictionSim2D aiida export --material WSe2 --layers 2 --output wse2_bilayer.aiida
```

### aiida import-archive

Import AiiDA archive from another system.

```bash
FrictionSim2D aiida import-archive ARCHIVE_FILE
```

**Arguments**:
- `ARCHIVE_FILE`: Path to `.aiida` archive file

**Examples**:

```bash
# Import archive
FrictionSim2D aiida import-archive friction_archive.aiida

# Import from colleague
FrictionSim2D aiida import-archive /path/to/shared_results.aiida
```

### aiida package

Package simulations with provenance into tarball.

```bash
FrictionSim2D aiida package SIMULATION_DIR [OPTIONS]
```

**Arguments**:
- `SIMULATION_DIR`: Simulation root directory

**Options**:
- `--output FILE`: Tarball filename (default: simulations.tar.gz)

**Examples**:

```bash
# Create tarball
FrictionSim2D aiida package ./output --output simulations.tar.gz

# Package with timestamp
FrictionSim2D aiida package ./output --output archive_$(date +%Y%m%d).tar.gz
```

---

## Command Combinations

### Full Local Workflow

```bash
# 1. Generate simulations with AiiDA provenance
FrictionSim2D run afm config.ini --aiida

# 2. Submit to cluster
FrictionSim2D aiida submit ./output/simulation_20250201_120000

# 3. Monitor status
FrictionSim2D aiida status

# 4. Query results
FrictionSim2D aiida query --material MoS2

# 5. Export archive
FrictionSim2D aiida export --output project_results.aiida
```

### Offline HPC Workflow

```bash
# 1. Generate with HPC scripts
FrictionSim2D run afm config.ini --aiida --hpc-scripts

# 2. Transfer to HPC manually
# scp -r ./output user@hpc:~/simulations/

# 3. Run on HPC
# ssh user@hpc
# cd ~/simulations/output/simulation_20250201_120000/hpc
# ./submit_jobs.sh

# 4. Transfer results back
# scp -r user@hpc:~/simulations/output ./returned_results

# 5. Import results
FrictionSim2D aiida import ./returned_results
```

### Batch Processing

```bash
# Generate multiple configs
for config in configs/*.ini; do
    FrictionSim2D run afm $config --aiida
done

# Submit all
for sim in ./output/*/; do
    FrictionSim2D aiida submit $sim
done

# Query combined results
FrictionSim2D aiida query --format csv --output all_results.csv
```

### Testing Workflow

```bash
# 1. Test with small config
FrictionSim2D run afm test_config.ini --aiida

# 2. Preview submission
FrictionSim2D aiida submit ./output --dry-run

# 3. Submit test
FrictionSim2D aiida submit ./output

# 4. Check if successful
FrictionSim2D aiida status

# 5. If good, run full sweep
FrictionSim2D run afm full_config.ini --aiida
FrictionSim2D aiida submit ./output
```

---

## See Also

- [Configuration Guide](configuration_guide.md) - Config file format
- [AiiDA Workflows](aiida_workflows.md) - Detailed AiiDA usage
- [Python API Guide](python_api_guide.md) - Programmatic usage
- [Settings Reference](settings_reference.md) - Settings configuration
- [Examples](examples.md) - Complete working examples
