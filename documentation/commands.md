# FrictionSim2D Commands

\anchor commands

This page summarizes the CLI interface.

\section cmd_main Main entrypoint

```bash
FrictionSim2D --help
FrictionSim2D --version
```

\section cmd_run run group

\subsection cmd_run_afm run afm

```bash
FrictionSim2D run afm CONFIG_FILE \
  [--output-dir DIR] [--aiida] [--hpc-scripts] [--hpc NAME] [--local]
```

Generates AFM simulations.

\subsection cmd_run_sheet run sheetonsheet

```bash
FrictionSim2D run sheetonsheet CONFIG_FILE \
  [--output-dir DIR] [--aiida] [--hpc-scripts] [--hpc NAME] [--local]
```

Generates sheet-on-sheet simulations.

\section cmd_hpc hpc group

\subsection cmd_hpc_generate hpc generate

```bash
FrictionSim2D hpc generate SIMULATION_DIR [--scheduler pbs|slurm] [--output-dir DIR]
```

Scans existing simulations and emits batch scripts/manifests.

\section cmd_settings settings group

```bash
FrictionSim2D settings show
FrictionSim2D settings init
FrictionSim2D settings reset
```

\section cmd_aiida aiida group

\subsection cmd_aiida_status aiida status

```bash
FrictionSim2D aiida status
```

\subsection cmd_aiida_setup aiida setup

```bash
FrictionSim2D aiida setup [--profile NAME] [--lammps-path PATH] [--hpc-config PATH]
```

\subsection cmd_aiida_submit aiida submit

```bash
FrictionSim2D aiida submit SIMULATION_DIR \
  [--code CODE@COMPUTER] [--scripts CSV] [--array] [--scheduler pbs|slurm] \
  [--machines N] [--mpiprocs N] [--walltime HH:MM:SS|SECONDS] \
  [--queue NAME] [--project NAME] [--mem VALUE] [--prepend-text LINE] [--dry-run]
```

\subsection cmd_aiida_import aiida import

```bash
FrictionSim2D aiida import RESULTS_DIR [--process/--no-process]
```

\subsection cmd_aiida_query aiida query

```bash
FrictionSim2D aiida query [--material MAT] [--layers N] [--force F] \
  [--format table|csv|json] [--output FILE]
```

\subsection cmd_aiida_export aiida export

```bash
FrictionSim2D aiida export [--output FILE.aiida] [--material MAT]
```

\subsection cmd_aiida_import_archive aiida import-archive

```bash
FrictionSim2D aiida import-archive ARCHIVE.aiida
```

\subsection cmd_aiida_package aiida package

```bash
FrictionSim2D aiida package SIMULATION_DIR [--output FILE.tar.gz]
```
