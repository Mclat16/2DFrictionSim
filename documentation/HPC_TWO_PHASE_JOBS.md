# Two-Phase HPC Job Submission

## Overview

AFM simulations now use a two-phase job submission system to ensure all `system.in` initialization scripts complete before any `slide*.in` simulation scripts run.

## How It Works

### 1. Manifest Creation
The system creates a manifest listing all simulation jobs:
- **Phase 1**: All `system*.in` files are listed first
- **Phase 2**: All `slide*.in` files are listed second

### 2. Separate Job Scripts
Two separate HPC job scripts are generated:
- `run_system.pbs` or `run_system.sh` - Runs all system initialization jobs
- `run_slide.pbs` or `run_slide.sh` - Runs all slide simulation jobs

### 3. Job Dependencies
The slide job script has a dependency on the system job:
- **SLURM**: `--dependency=afterok:$SYSTEM_JOB_ID`
- **PBS**: `-W depend=afterok:$SYSTEM_JOB_ID`

This ensures slide jobs wait for all system jobs to complete successfully.

### 4. Submission Script
A submission wrapper script `submit_jobs.sh` is generated that:
1. Submits the system job
2. Captures the job ID
3. Submits the slide job with dependency on the system job

## Usage

### For AFM Simulations

```bash
cd your_simulation_directory

# Submit both phases (system jobs will run first)
./hpc/submit_jobs.sh

# Monitor jobs
squeue -u $USER  # SLURM
qstat -u $USER   # PBS
```

### For Sheet-on-Sheet Simulations

Sheet-on-sheet simulations don't have system initialization scripts, so they use simple single-phase submission:

```bash
cd your_simulation_directory

# Submit slide jobs directly
sbatch hpc/run.sh   # SLURM
qsub hpc/run.pbs    # PBS
```

## Files Generated

In the `hpc/` directory:
- `manifest.json` - Full manifest with all job metadata
- `manifest_system.txt` - List of system script paths (AFM only)
- `manifest_slide.txt` - List of slide script paths
- `run_system.pbs/sh` - System job script (AFM only)
- `run_slide.pbs/sh` - Slide job script
- `submit_jobs.sh` - Automated submission script

## Benefits

1. **Correctness**: Guarantees proper execution order
2. **Efficiency**: No polling or waiting in job scripts
3. **Native dependencies**: Uses scheduler features (afterok)
4. **Parallelism**: System jobs run in parallel, then slide jobs run in parallel
5. **Clean separation**: Easy to monitor each phase independently
