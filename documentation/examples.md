# Examples

\anchor examples

\section ex_local Local generation examples

AFM generation:

```bash
FrictionSim2D run afm examples/afm_config.ini --output-dir ./simulation_output
```

Sheet-on-sheet generation:

```bash
FrictionSim2D run sheetonsheet examples/sheet_config.ini --output-dir ./simulation_output
```

\section ex_hpc Generate HPC scripts for existing runs

PBS:

```bash
FrictionSim2D hpc generate ./simulation_output/simulation_YYYYMMDD_HHMMSS --scheduler pbs
```

SLURM:

```bash
FrictionSim2D hpc generate ./simulation_output/simulation_YYYYMMDD_HHMMSS --scheduler slurm
```

\section ex_aiida_setup AiiDA setup example

```bash
FrictionSim2D aiida setup --profile friction2d --hpc-config src/data/settings/hpc.yaml
```

\section ex_aiida_submit AiiDA submit examples

Submit one CalcJob per simulation:

```bash
FrictionSim2D aiida submit ./simulation_output/simulation_YYYYMMDD_HHMMSS --code lammps@localhost
```

Submit as an array job:

```bash
FrictionSim2D aiida submit ./simulation_output/simulation_YYYYMMDD_HHMMSS \
  --code lammps@localhost --array --scheduler pbs
```

\section ex_aiida_results Import/query/export examples

Import completed results:

```bash
FrictionSim2D aiida import ./returned_results
```

Query by material:

```bash
FrictionSim2D aiida query --material h-MoS2 --format table
```

Export archive:

```bash
FrictionSim2D aiida export --output friction2d_results.aiida
```

Import archive:

```bash
FrictionSim2D aiida import-archive friction2d_results.aiida
```
