def pbs(self):
    pbs_type = ['system', 'slide']
    for layer in self.var['2D']['layers']:
        for type in pbs_type:
            filename = f"{self.scripts}/{self.var['2D']['mat']}_{type}.pbs"
            PBS = '"${PBS_ARRAY_INDEX}p"'
            with open(f"{self.scripts}/list_{type}_{layer}", 'r') as f:
                n = len(f.readlines())
            with open(filename, 'w') as f:
                f.writelines([
                    "#!/bin/bash\n",
                    "#PBS -l select=1:ncpus=32:mem=62gb:mpiprocs=32:cpu_type=rome\n",
                    "#PBS -l walltime=08:00:00\n",
                    f"#PBS -J 1-{n}\n",
                    f"#PBS -o /rds/general/user/mv923/home/logs_{type}/\n",
                    f"#PBS -e /rds/general/user/mv923/home/logs_{type}/\n\n",
                    "module purge\n",
                    "module load tools/dev\n",
                    "module load LAMMPS/23Jun2022-foss-2021b-kokkos\n",
                    "#module load OpenMPI/4.1.4-GCC-11.3.0\n\n",
                    "#Go to the temp directory (ephemeral) and create a new folder for this run\n",
                    "cd $EPHEMERAL\n\n",
                    "# $PBS_O_WORKDIR is the directory where the pbs script was sent from. Copy everything from the work directory to the temporary directory to prepare for the run\n\n",
                    f"mpiexec lmp -l none -in $(sed -n {PBS} scripts/afm2/scripts/list_{type}_{layer})\n\n",
                ])
    filename = f"{self.scripts}/{self.var['2D']['mat']}_transfer.pbs"
    with open(filename, 'w') as f:
        f.writelines([
            "#!/bin/bash\n",
            "#PBS -l select=1:ncpus=1:mem=62gb:cpu_type=rome\n",
            "#PBS -l walltime=00:30:00\n\n",
            f"#PBS -o /rds/general/user/mv923/home/scripts/\n",
            f"#PBS -e /rds/general/user/mv923/home/scripts/\n\n",
            "cd $HOME\n",
            f"mkdir -p logs_system/\n\n",
            f"mkdir -p logs_slide/\n\n",
            "cd $EPHEMERAL\n",
            f"mkdir -p {self.var['dir']}/\n\n",
            f"cp -r $PBS_O_WORKDIR/{self.var['dir']}/* {self.var['dir']}\n",
            "cp -r $PBS_O_WORKDIR/tribo_2D/Potentials/ .\n"
        ])
    filename = f"{self.scripts}/{self.var['2D']['mat']}_transfer2.pbs"
    with open(filename, 'w') as f:
        f.writelines([
            "#!/bin/bash\n",
            "#PBS -l select=1:ncpus=1:mem=62gb:cpu_type=rome\n",
            "#PBS -l walltime=00:30:00\n\n",
            f"#PBS -o /rds/general/user/mv923/home/scripts/\n",
            f"#PBS -e /rds/general/user/mv923/home/scripts/\n\n",
            "cd $EPHEMERAL\n",
            "#After the end of the run copy everything back to the parent directory\n",
            f"cp -r ./scripts/afm/* $PBS_O_WORKDIR/scripts/afm\n\n",
            f"rm -r ./scripts/afm\n\n"
        ])
    filename = f"{self.scripts}/{self.var['2D']['mat']}_instructions.txt"
    with open(filename, 'w') as f:
        f.writelines([
            f"# The first step is transferring the whole {self.var['2D']['mat']} folder to the RDS Home Directory\n",
            "# This can be done by adding the RDS Path to your file system as seen in\n",
            "# https://icl-rcs-user-guide.readthedocs.io/en/latest/rds/paths/ \n\n",
            "# Next, we need to transfer the files to the Ephemeral directory, run the following command:\n",
            f"qsub {self.scripts}/{self.var['2D']['mat']}_transfer.pbs\n\n",
            "# Once this is done, you can run the system intialisation as follows:\n",
            f"qsub -W depend=afterok:XXXX.pbs {self.scripts}/{self.var['2D']['mat']}_system.pbs\n\n",
            "# Where XXXX.pbs is the job number given to you after submitting transfer.pbs\n\n",
            "# Then we can run the loading as follows:\n",
            f"qsub -W depend=afterany:XXXX[].pbs {self.scripts}/{self.var['2D']['mat']}_load.pbs\n\n",
            "# Where XXXX[].pbs is the job number given to you after submitting system.pbs\n\n",
            "# Finally, we can run the sliding as follows:\n",
            f"qsub -W depend=afterany:XXXX[].pbs {self.scripts}/{self.var['2D']['mat']}_slide.pbs\n\n",
            "# Where XXXX[].pbs is the job number given to you after submitting load.pbs\n\n",
            "# Transfer your results back to the home directory with:\n",
            f"qsub -W depend=afterany:XXXX[].pbs {self.scripts}/{self.var['2D']['mat']}_transfer2.pbs\n\n",
            "# Where XXXX[].pbs is the job number given to you after submitting slide.pbs\n\n",
            "# Make sure to transfer your results and visuals back to your personal computer\n"
        ])