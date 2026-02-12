# Introduction

\anchor main

\section intro What is FrictionSim2D?

FrictionSim2D is a simulation setup and workflow tool for atomistic friction studies of 2D materials using LAMMPS.
It generates reproducible simulation folders, input scripts, provenance artifacts, and optional HPC/AiiDA workflows.

The project supports two main experiment families:

- AFM (tip-on-sheet/substrate)
- Sheet-on-sheet sliding

Typical use cases include parameter sweeps over material, layer count, force/pressure, temperature, scan angle, and scan speed.

\section architecture Core workflow

A standard FrictionSim2D run follows this sequence:

1. Parse and expand input configuration sweeps.
2. Build geometry and potential assets.
3. Write LAMMPS input files and structured run directories.
4. Optionally generate HPC submission scripts.
5. Optionally register provenance and metadata in AiiDA.
6. Optionally submit/monitor/import through AiiDA.

\section layout Output layout and reproducibility

FrictionSim2D writes run outputs under a simulation root (timestamped by default), including:

- Simulation directories with `lammps/`, `data/`, `results/`, `visuals/`, and `provenance/`
- Optional `hpc/` scripts for array/batch execution
- Provenance metadata (`manifest.json`, config snapshots, copied material/potential sources)

This structure is designed to keep runs portable and auditable.

\section quickstart Quick start

Basic local generation:

```bash
FrictionSim2D run afm afm_config.ini --output-dir ./simulation_output
FrictionSim2D run sheetonsheet sheet_config.ini --output-dir ./simulation_output
```

Generate with provenance tracking in AiiDA:

```bash
FrictionSim2D run afm afm_config.ini --aiida --output-dir ./simulation_output
```

Generate HPC scripts while building simulations:

```bash
FrictionSim2D run afm afm_config.ini --hpc-scripts --output-dir ./simulation_output
```

\section cli Command groups

\subsection cli_run Simulation generation

```bash
FrictionSim2D run afm CONFIG_FILE [--output-dir DIR] [--aiida] [--hpc-scripts]
FrictionSim2D run sheetonsheet CONFIG_FILE [--output-dir DIR] [--aiida] [--hpc-scripts]
```

\subsection cli_hpc HPC script generation

```bash
FrictionSim2D hpc generate SIMULATION_DIR [--scheduler pbs|slurm] [--output-dir DIR]
```

\subsection cli_settings Settings management

```bash
FrictionSim2D settings show
FrictionSim2D settings init
FrictionSim2D settings reset
```

\subsection cli_aiida AiiDA workflow commands

```bash
FrictionSim2D aiida status
FrictionSim2D aiida setup [--profile NAME] [--lammps-path PATH] [--hpc-config PATH]
FrictionSim2D aiida submit SIMULATION_DIR [--code CODE@COMPUTER] [--array]
FrictionSim2D aiida import RESULTS_DIR
FrictionSim2D aiida query [--material MAT] [--layers N] [--force F]
FrictionSim2D aiida export [--output FILE] [--material MAT]
FrictionSim2D aiida import-archive ARCHIVE.aiida
FrictionSim2D aiida package SIMULATION_DIR [--output FILE.tar.gz]
```

\section aiida AiiDA modes and recommendations

FrictionSim2D supports AiiDA for provenance, archival export/import, and scheduler submission.

Recommended execution modes:

- **Local/HPC-native AiiDA**: run AiiDA directly on the HPC environment (preferred for secure clusters).
- **Remote AiiDA via SSH transport**: feasible where cluster auth policy permits non-interactive auth.
- **Offline mode**: generate and run via scripts, then import results later.

For clusters with strict authentication constraints, HPC-native AiiDA deployment is usually more robust than local-to-remote SSH transport.

\section hpc HPC script behavior

HPC script templates support PBS and SLURM arrays, module loading, optional scratch staging, and result rsync/copy-back patterns.

Configurable fields include:

- scheduler type, queue/partition/account
- nodes/CPUs/memory/walltime
- module list and MPI launcher command
- scratch directory usage
- list/order of LAMMPS scripts to execute

\section docs Additional docs

- `documentation/installation.md`: Conda-only installation workflow (required)
- `documentation/essentials.md`: core concepts and run lifecycle
- `documentation/commands.md`: CLI command reference
- `documentation/examples.md`: practical end-to-end examples
- `documentation/PROVENANCE_ARCHITECTURE.md`: provenance data model and file-level traceability

\section install_policy Installation policy

FrictionSim2D documentation assumes Conda-based installation and execution.
This is required to ensure consistent availability of LAMMPS/Atomsk and the
optional AiiDA service stack.

\section support Support and contribution

For issues or feature requests, open a GitHub issue in the FrictionSim2D repository.
When reporting bugs, include:

- command used
- relevant config file
- scheduler template (if HPC)
- error output/log snippets

\section citation Citation guidance

If this software is used in published work, cite:

- FrictionSim2D repository/version used
- LAMMPS (as the simulation engine)
- AiiDA (if provenance/workflow features are used)
