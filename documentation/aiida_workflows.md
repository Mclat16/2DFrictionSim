# AiiDA Workflows Guide

\anchor aiida_workflows

## Overview

FrictionSim2D integrates with [AiiDA](https://www.aiida.net) for:
- **Provenance tracking**: Full reproducibility with data lineage
- **HPC job submission**: Automated submission to PBS/SLURM clusters
- **Result management**: Import, query, and export simulation results
- **Archive workflows**: Transfer data between systems

This guide covers the **new simplified interface** introduced in v0.2.0, which reduces AiiDA usage from 68 lines to 5 lines.

## Why AiiDA?

**Without AiiDA**:
- Manual job submission via shell scripts
- No automatic result retrieval
- Manual tracking of simulation parameters
- Difficult to reproduce years later

**With AiiDA**:
- Automatic job submission and monitoring
- Results automatically imported to database
- Full provenance graph stored
- Export/import archives for data transfer

## Quick Start

### 1. Setup AiiDA (One-Time)

```bash
# Initialize AiiDA with RabbitMQ
FrictionSim2D aiida setup --profile friction2d

# Configure LAMMPS code and computer
# (Interactive - will prompt for details)
```

This command:
1. Starts RabbitMQ message broker
2. Creates AiiDA profile with PostgreSQL
3. Configures localhost computer
4. Sets up LAMMPS code

### 2. Run Simulation with AiiDA

**Python API (Recommended)**:

```python
from src.aiida.submit import run_with_aiida

# Generate and submit with one call
sims, root, nodes = run_with_aiida(
    'afm_config.ini',
    model='afm',
)

print(f"Submitted {len(nodes)} jobs to AiiDA")
```

**CLI**:

```bash
# Generate simulations
FrictionSim2D run afm afm_config.ini --aiida

# Submit to cluster
FrictionSim2D aiida submit ./output/simulation_20250201_120000

# Monitor status
FrictionSim2D aiida status
```

### 3. Query and Export Results

```bash
# Query results
FrictionSim2D aiida query --material MoS2 --format table

# Export archive
FrictionSim2D aiida export --output results.aiida
```

## Simplified AiiDA Interface

### Before: Manual Workflow (68 lines)

```python
# Old approach - LOTS of boilerplate
from pathlib import Path
from aiida.manage.configuration import load_profile, get_profile
from aiida.orm import load_code, QueryBuilder, Code
from aiida.common.exceptions import NotExistent

# Load profile
try:
    profile = get_profile()
    if profile is None or profile.name != 'friction2d':
        load_profile('friction2d')
except Exception:
    load_profile('friction2d')

# Find or setup code
qb = QueryBuilder()
qb.append(Code, filters={'label': {'like': '%lammps%'}})
codes = [c for [c] in qb.all()]

if not codes:
    raise RuntimeError("No LAMMPS code configured")
elif len(codes) > 1:
    print("Multiple codes found, select one:")
    for i, code in enumerate(codes):
        print(f"{i+1}. {code.full_label}")
    choice = int(input("Choice: ")) - 1
    code = codes[choice]
else:
    code = codes[0]

# Find simulation directories
from src import AFMSimulation
sim_root = Path('./output/simulation_20250201_120000')
sim_dirs = [d for d in sim_root.glob('sim_*') if (d / 'lammps').exists()]

# Build resource dict manually
from src.core.config import load_settings
settings = load_settings()

resources = {
    'num_machines': settings.hpc.num_nodes,
    'num_mpiprocs_per_machine': settings.hpc.num_cpus,
}

options = {
    'resources': resources,
    'max_wallclock_seconds': settings.hpc.walltime_hours * 3600,
}

if settings.hpc.queue:
    options['queue_name'] = settings.hpc.queue
if settings.hpc.account:
    options['account'] = settings.hpc.account

# Build prepend_text from modules
if settings.hpc.modules:
    prepend = '\\n'.join(f'module load {m}' for m in settings.hpc.modules)
    options['prepend_text'] = prepend

# Submit batch
from src.aiida.calcjob import submit_batch
processes = submit_batch(
    simulation_dirs=sim_dirs,
    code_label=code,
    options=options,
)

print(f"Submitted {len(processes)} jobs")
```

### After: Simplified Interface (5 lines)

```python
from src.aiida.submit import run_with_aiida

sims, root, nodes = run_with_aiida(
    'afm_config.ini', model='afm'
)
```

**What changed**:
- ✅ Auto-detects AiiDA profile
- ✅ Auto-detects LAMMPS code (or prompts if multiple)
- ✅ Uses defaults from settings.yaml
- ✅ Auto-submits by default (configurable)
- ✅ Returns everything you need in one call

## CLI Commands

### Setup

```bash
# Basic setup (localhost, local computer)
FrictionSim2D aiida setup

# With specific profile name
FrictionSim2D aiida setup --profile my_friction_profile

# With custom LAMMPS path
FrictionSim2D aiida setup --lammps-path /opt/lammps/bin/lmp

# Configure remote HPC computer (from settings.yaml)
FrictionSim2D aiida setup --use-remote
```

### Submit

**New simplified interface**:

```bash
# Minimal (auto-detect code, use defaults)
FrictionSim2D aiida submit ./output

# With overrides
FrictionSim2D aiida submit ./output --machines 4 --walltime 24:00:00

# Preview before submitting
FrictionSim2D aiida submit ./output --dry-run

# Array job (single job for all simulations)
FrictionSim2D aiida submit ./output --array

# Manual code specification
FrictionSim2D aiida submit ./output --code lammps@hpc
```

**Interactive prompting**: If code not specified and multiple codes exist, you'll be prompted:

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

### Status

```bash
# Check AiiDA daemon and recent jobs
FrictionSim2D aiida status

# Sample output:
# Daemon: Running
# Recent calculations:
#   PK=1234  afm_MoS2_1L_5nN      State: running
#   PK=1235  afm_MoS2_2L_10nN     State: finished
```

### Query

```bash
# Query all simulations
FrictionSim2D aiida query

# Filter by material
FrictionSim2D aiida query --material MoS2

# Filter by parameters
FrictionSim2D aiida query --layers 2 --force 10

# Output formats
FrictionSim2D aiida query --format table   # Default
FrictionSim2D aiida query --format csv
FrictionSim2D aiida query --format json

# Save to file
FrictionSim2D aiida query --material MoS2 --output results.csv
```

### Import Results

```bash
# Import completed results from HPC
FrictionSim2D aiida import ./returned_results

# Skip post-processing
FrictionSim2D aiida import ./results --no-process
```

### Export/Import Archives

```bash
# Export archive (all data)
FrictionSim2D aiida export --output friction_archive.aiida

# Export filtered
FrictionSim2D aiida export --material MoS2 --output mos2_only.aiida

# Import archive on another system
FrictionSim2D aiida import-archive friction_archive.aiida
```

### Package Simulations

```bash
# Create tarball with provenance
FrictionSim2D aiida package ./output --output simulations.tar.gz
```

## Execution Modes

### 1. Offline Mode (Default)

Generate simulations locally, run manually on HPC, import results later:

```bash
# Generate with provenance
FrictionSim2D run afm config.ini --aiida

# Transfer to HPC manually
scp -r ./output user@hpc:~/simulations/

# Run on HPC (manual)
# ... use HPC scripts or run directly ...

# Transfer results back
scp -r user@hpc:~/simulations/output ./returned_results

# Import to AiiDA
FrictionSim2D aiida import ./returned_results
```

**Pros**: Works on secured clusters, no SSH setup needed
**Cons**: Manual transfer steps

### 2. Local Mode

Run AiiDA directly where simulations execute:

```bash
# On your local machine or HPC login node
FrictionSim2D run afm config.ini --aiida

# Submit via AiiDA (local daemon manages jobs)
FrictionSim2D aiida submit ./output --code lammps@localhost
```

**Pros**: Fully automated, AiiDA manages everything
**Cons**: Requires AiiDA daemon on execution environment

### 3. Remote Mode (Advanced)

Run AiiDA locally, submit to remote HPC via SSH:

**Setup**:

```yaml
# In settings.yaml
aiida:
    transport: 'ssh'
    hostname: 'login.hpc.example.edu'
    username: 'your_username'
    key_filename: '~/.ssh/id_rsa'
    workdir: '/scratch/username/aiida_work'
```

```bash
# Setup remote computer
FrictionSim2D aiida setup --use-remote

# Submit jobs (AiiDA handles SSH)
FrictionSim2D aiida submit ./output --code lammps@hpc
```

**Pros**: Run AiiDA locally while computing remotely
**Cons**: Requires SSH access, key-based auth, may violate cluster policies

## Python API Examples

### Basic Workflow

```python
from src.aiida.submit import run_with_aiida

# Generate and submit
sims, root, nodes = run_with_aiida(
    config_file='afm_config.ini',
    model='afm',
)

# Wait for completion (in real workflow, daemon handles this)
from aiida import engine
for node in nodes:
    print(f"Job {node.pk}: {node.get_state()}")
```

### Generate Without Submitting

```python
# Generate files with provenance, but don't submit
sims, root, _ = run_with_aiida(
    'config.ini',
    model='afm',
    auto_submit=False,  # Don't submit
)

# Submit later manually
from src.aiida.calcjob import submit_batch
from aiida.orm import load_code

code = load_code('lammps@hpc')
nodes = submit_batch(sims, code)
```

### Array Job Submission

```python
# Submit all simulations as single array job
sims, root, nodes = run_with_aiida(
    'config.ini',
    model='afm',
    use_array=True,         # Array job
)

# nodes will contain a single ProcessNode
print(f"Array job PK: {nodes[0].pk}")
```

### Query Results

```python
from aiida.orm import QueryBuilder, Dict

# Query simulations by material
qb = QueryBuilder()
qb.append(Dict, filters={'attributes.material': 'MoS2'})
results = qb.all()

print(f"Found {len(results)} MoS2 simulations")
```

## Best Practices

### 1. Test Locally First

```python
# Test with small config first
test_config = 'test_config.ini'  # Single simulation
sims, root, nodes = run_with_aiida(test_config)

# Verify output before scaling up
if nodes[0].is_finished_ok:
    # Good! Now run full sweep
    sims, root, nodes = run_with_aiida('full_config.ini')
```

### 2. Use Dry-Run

```bash
# Preview what will be submitted
FrictionSim2D aiida submit ./output --dry-run

# Check output, then submit for real
FrictionSim2D aiida submit ./output
```

### 3. Monitor Jobs

```bash
# Check daemon status
FrictionSim2D aiida status

# Or use verdi directly
verdi process list
verdi process show 1234
```

### 4. Archive Completed Work

```bash
# Export archives periodically
FrictionSim2D aiida export --output archive_2025_Q1.aiida

# Store archive safely (backup)
cp archive_2025_Q1.aiida /backup/location/
```

## Troubleshooting

### "No LAMMPS codes found"

```bash
# Check configured codes
verdi code list

# Setup code if missing
FrictionSim2D aiida setup
```

### "AiiDA profile not loaded"

```python
# Explicitly load profile
from aiida import load_profile
load_profile('friction2d')

# Or use profile_name parameter
sims, root, nodes = run_with_aiida('config.ini', profile_name='friction2d')
```

### "Daemon not running"

```bash
# Start daemon
verdi daemon start

# Check status
verdi daemon status
```

### "Failed to submit: connection refused"

Check RabbitMQ is running:

```bash
rabbitmqctl status

# If not running
rabbitmq-server -detached
```

### Job stuck in "waiting" state

```bash
# Check daemon logs
verdi daemon logshow

# Restart daemon
verdi daemon restart
```

## Migration Guide

### From Old Interface

**Old code**:
```python
# 68 lines of setup...
processes = submit_batch(dirs, code, options={'resources': {...}})
```

**New code**:
```python
from src.aiida.submit import run_with_aiida
sims, root, nodes = run_with_aiida('config.ini')
```

### From Manual HPC Scripts

**Old workflow**:
1. Generate simulations
2. Generate HPC scripts
3. Transfer to HPC
4. Submit manually
5. Monitor manually
6. Transfer results back

**New workflow**:
```python
# One command does everything
sims, root, nodes = run_with_aiida('config.ini')

# AiiDA handles submission, monitoring, retrieval
```

## See Also

- [Python API Guide](python_api_guide.md) - Full API reference
- [Settings Reference](settings_reference.md) - Configure settings
- [Configuration Guide](configuration_guide.md) - Simulation config files
- [AiiDA Documentation](https://aiida.readthedocs.io) - Official AiiDA docs
