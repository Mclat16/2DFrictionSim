# FrictionSim2D

FrictionSim2D generates and manages LAMMPS friction simulation workflows for 2D materials.
It supports AFM and sheet-on-sheet setups, HPC script generation, and optional AiiDA provenance/submission workflows.

## Installation (Conda-only)

This project is intended to run from a Conda environment so that LAMMPS, Atomsk, and AiiDA service dependencies are consistent.

> pip installation is not the supported path in this repository documentation.

### 1) Create environment

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

### 2) Run from source

From repository root:

```bash
export PYTHONPATH=$PWD
python -m src.cli --help
```

Optional alias:

```bash
alias FrictionSim2D='python -m src.cli'
```

### 3) Verify binaries

```bash
python -m src.cli --help
lmp -h
atomsk --version
verdi --version
```

## Quick start

Generate AFM simulations:

```bash
FrictionSim2D run afm examples/afm_config.ini --output-dir ./simulation_output
```

Generate sheet-on-sheet simulations:

```bash
FrictionSim2D run sheetonsheet examples/sheet_config.ini --output-dir ./simulation_output
```

Generate with AiiDA registration enabled:

```bash
FrictionSim2D run afm examples/afm_config.ini --aiida --output-dir ./simulation_output
```

Generate HPC scripts:

```bash
FrictionSim2D hpc generate ./simulation_output/simulation_YYYYMMDD_HHMMSS --scheduler pbs
```

## CLI overview

- `FrictionSim2D run afm ...`
- `FrictionSim2D run sheetonsheet ...`
- `FrictionSim2D hpc generate ...`
- `FrictionSim2D settings show|init|reset`
- `FrictionSim2D aiida status|setup|submit|import|query|export|import-archive|package`

## AiiDA notes

- Use `FrictionSim2D aiida setup` for first-time profile/computer/code setup.
- For secure HPC clusters, running AiiDA natively on the HPC environment is often more robust than local SSH transport.
- Use archive transfer when needed: `aiida export` on source environment and `aiida import-archive` on target.

## Output structure

Generated simulation roots typically contain:

- `afm/` or `sheetonsheet/` runs
- per-run `lammps/`, `data/`, `results/`, `visuals/`, `provenance/`
- optional `hpc/` submission scripts

## Documentation

- [documentation/mainpage.md](documentation/mainpage.md)
- [documentation/installation.md](documentation/installation.md)
- [documentation/essentials.md](documentation/essentials.md)
- [documentation/commands.md](documentation/commands.md)
- [documentation/examples.md](documentation/examples.md)
- [documentation/PROVENANCE_ARCHITECTURE.md](documentation/PROVENANCE_ARCHITECTURE.md)

## Development

Run tests:

```bash
pytest -v
```

Run lint (example):

```bash
pylint src/aiida
```
