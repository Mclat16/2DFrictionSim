# Installation (Conda-only)

\anchor installation

\section install_scope Scope

This project is supported through Conda environments.
Conda is required because LAMMPS, Atomsk, and the AiiDA service stack are expected from Conda packages.

> **Important:** pip-based installation is intentionally not supported in this guide.

\section install_prereq Prerequisites

- Linux system
- Conda or Miniconda installed
- Access to `conda-forge` channel

\section install_env Create the environment

```bash
conda create -n frictionsim2d -c conda-forge \
  python=3.11 \
  numpy ase pyyaml jinja2 pydantic click pandas \
  lammps atomsk \
  aiida-core aiida-core.services typing_extensions psycopg2
```

```bash
conda activate frictionsim2d
```

\section install_source Use from source (no pip)

From repository root:

```bash
export PYTHONPATH=$PWD
python -m src.cli --help
```

Optional shell alias:

```bash
alias FrictionSim2D='python -m src.cli'
```

\section install_verify Verify tools

```bash
python -m src.cli --help
lmp -h
atomsk --version
verdi --version
```

\section install_aiida First AiiDA bootstrap

Profile setup (PostgreSQL-backed):

```bash
rabbitmq-server -detached
verdi presto --use-postgres --profile-name friction2d
```

Check status:

```bash
verdi profile list
verdi daemon status
```

\section install_notes Notes for secure HPC clusters

If direct local-to-HPC AiiDA SSH transport is restricted by cluster policy, run AiiDA natively on the HPC environment and use archive export/import for transfer workflows.

\section install_troubleshooting Troubleshooting

- `lmp: command not found`: confirm env is active and `lammps` is installed in this env.
- `verdi` profile errors: rerun `verdi presto --use-postgres` in the same env.
- service issues: confirm `aiida-core.services` is installed from Conda.
