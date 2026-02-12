# Essentials

\anchor essentials

\section essentials_flow Standard FrictionSim2D flow

1. Prepare config (`afm_config.ini` or `sheet_config.ini`).
2. Generate simulations with `run` commands.
3. Optionally generate HPC scripts.
4. Optionally register/submit via AiiDA.
5. Import and query results.

\section essentials_inputs Inputs

Primary inputs are `.ini` config files plus material/potential assets referenced by those configs.

Typical run commands:

```bash
FrictionSim2D run afm afm_config.ini --output-dir ./simulation_output
FrictionSim2D run sheetonsheet sheet_config.ini --output-dir ./simulation_output
```

\section essentials_outputs Outputs

Generated run directories usually contain:

- `lammps/` (input scripts)
- `data/` (structures/data files)
- `results/` (numeric outputs)
- `visuals/` (trajectory/visual artifacts)
- `provenance/` (manifest + reproducibility metadata)

\section essentials_hpc HPC execution model

Use generated scripts (`hpc generate` or `--hpc-scripts`) for batch/array execution.
Templates support PBS and SLURM with module loading and optional scratch staging.

\section essentials_aiida AiiDA execution model

AiiDA can be used for:

- provenance registration
- scheduler submission (`aiida submit`)
- archive export/import
- query workflows

For secured clusters, HPC-native AiiDA deployment is typically more robust than local SSH transport.

\section essentials_repro Reproducibility checklist

- Keep original config file.
- Keep generated `provenance/manifest.json` and config snapshots.
- Record Conda environment (`conda env export > env.yml`).
- Version-control template and settings changes.
