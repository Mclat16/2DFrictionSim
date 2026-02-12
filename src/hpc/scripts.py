"""HPC script generation for PBS and SLURM schedulers.

This module generates batch job scripts for running LAMMPS simulations
on HPC clusters, supporting both PBS and SLURM schedulers.
"""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
import shutil
from typing import Any, Dict, List, Literal, Optional

from jinja2 import Environment, FileSystemLoader


TEMPLATES_DIR = Path(__file__).parent.parent / 'templates' / 'hpc'


@dataclass
class HPCConfig:
    """Configuration for HPC job submission.
    
    Can be created from GlobalSettings.hpc or instantiated directly.
    """
    scheduler_type: Literal['pbs', 'slurm'] = 'pbs'
    nodes: int = 1
    cpus_per_node: int = 32
    memory_gb: int = 62
    walltime_hours: int = 20
    job_name: str = "friction2d"
    queue: Optional[str] = None
    partition: Optional[str] = None
    account: Optional[str] = None
    hpc_home: Optional[str] = None
    log_dir: Optional[str] = None
    scratch_dir: Optional[str] = "$TMPDIR"
    modules: List[str] = field(default_factory=lambda: [
        'tools/prod',
        'LAMMPS/29Aug2024-foss-2023b-kokkos'
    ])
    mpi_command: str = "mpirun"
    lmp_flags: str = "-l none"
    use_tmpdir: bool = True
    lammps_scripts: List[str] = field(default_factory=lambda: [
        'system.in',
        'slide.in'
    ])
    max_array_size: int = 300

    @classmethod
    def from_settings(cls, hpc_settings, job_name: str = "friction2d") -> 'HPCConfig':
        """Create HPCConfig from GlobalSettings.hpc."""
        return cls(
            scheduler_type=hpc_settings.scheduler_type,
            nodes=hpc_settings.num_nodes,
            cpus_per_node=hpc_settings.num_cpus,
            memory_gb=hpc_settings.memory_gb,
            walltime_hours=hpc_settings.walltime_hours,
            job_name=job_name,
            queue=hpc_settings.queue if hpc_settings.queue else None,
            partition=hpc_settings.partition,
            account=hpc_settings.account if hpc_settings.account else None,
            hpc_home=getattr(hpc_settings, 'hpc_home', None),
            log_dir=getattr(hpc_settings, 'log_dir', None),
            scratch_dir=getattr(hpc_settings, 'scratch_dir', None),
            modules=hpc_settings.modules,
            mpi_command=hpc_settings.mpi_command,
            use_tmpdir=hpc_settings.use_tmpdir,
            max_array_size=hpc_settings.max_array_size,
            lammps_scripts=getattr(hpc_settings, 'lammps_scripts', None)
            or ['system.in', 'slide.in'],
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for template rendering."""
        return {
            'nodes': self.nodes,
            'cpus_per_node': self.cpus_per_node,
            'memory_gb': self.memory_gb,
            'walltime': f"{self.walltime_hours}:00:00",
            'job_name': self.job_name,
            'queue': self.queue,
            'partition': self.partition,
            'account': self.account,
            'hpc_home': self.hpc_home,
            'log_dir': self.log_dir,
            'scratch_dir': self.scratch_dir,
            'modules': self.modules,
            'mpi_command': self.mpi_command,
            'lmp_flags': self.lmp_flags,
            'use_tmpdir': self.use_tmpdir,
            'lammps_scripts': self.lammps_scripts,
            'select_multi': f"1:ncpus={self.cpus_per_node}:mem={self.memory_gb}gb:mpiprocs={self.cpus_per_node}",
            'select_single': f"1:ncpus={self.cpus_per_node}:mem={self.memory_gb}gb",
            'ntasks_per_node': self.cpus_per_node,
            'cpus_per_task': 1,
            'mem': f"{self.memory_gb}G",
        }


class HPCScriptGenerator:
    """Generates HPC batch scripts for friction simulations.

    Supports PBS and SLURM schedulers, with automatic splitting of
    large job sets into multiple array jobs.
    """

    def __init__(self, config: Optional[HPCConfig] = None):
        """Initialize the script generator.

        Args:
            config: HPC configuration, uses defaults if not provided
        """
        self.config = config or HPCConfig()
        self.jinja_env = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            trim_blocks=True,
            lstrip_blocks=True
        )

    def generate_pbs_scripts(
            self,
            simulation_paths: List[str],
            output_dir: Path,
            base_dir: str = "$PBS_O_WORKDIR",
            log_dir: Optional[str] = None) -> List[Path]:
        """Generate PBS array job scripts.

        Args:
            simulation_paths: List of relative paths to simulation directories
            output_dir: Directory to write scripts to
            base_dir: Base directory for simulations on HPC
            log_dir: Directory for log files

        Returns:
            List of paths to generated script files
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        effective_log_dir = log_dir or self.config.log_dir
        if not effective_log_dir:
            raise ValueError("HPC log_dir is required for PBS script generation.")
        if not self.config.modules:
            raise ValueError("HPC modules list is empty. Set hpc.modules in settings.")
        if self.config.use_tmpdir and not self.config.scratch_dir:
            raise ValueError("HPC scratch_dir is required when use_tmpdir is true.")

        n_sims = len(simulation_paths)
        n_scripts = math.ceil(n_sims / self.config.max_array_size)

        scripts = []
        template = self.jinja_env.get_template('pbs_array.j2')

        for i in range(n_scripts):
            start_idx = i * self.config.max_array_size
            end_idx = min((i + 1) * self.config.max_array_size, n_sims)
            chunk = simulation_paths[start_idx:end_idx]

            manifest_name = f"manifest_{i+1}.txt"
            manifest_path = output_dir / manifest_name
            manifest_path.write_text('\n'.join(chunk))

            manifest_rel = f"{base_dir}/{output_dir.name}/{manifest_name}"
            context = self.config.to_dict()
            context.update({
                'array_size': len(chunk),
                'manifest_file': manifest_rel,
                'base_dir': base_dir,
                'log_dir': effective_log_dir,
            })

            if n_scripts > 1:
                context['job_name'] = f"{self.config.job_name}_{i+1}"

            script_content = template.render(context)
            script_name = f"run_{i+1}.pbs" if n_scripts > 1 else "run.pbs"
            script_path = output_dir / script_name
            script_path.write_text(script_content)
            scripts.append(script_path)

        self._write_master_script(output_dir, scripts, 'pbs')

        return scripts

    def generate_slurm_scripts(
            self,
            simulation_paths: List[str],
            output_dir: Path,
            base_dir: str = "$SLURM_SUBMIT_DIR",
            log_dir: Optional[str] = None) -> List[Path]:
        """Generate SLURM array job scripts.

        Args:
            simulation_paths: List of relative paths to simulation directories
            output_dir: Directory to write scripts to
            base_dir: Base directory for simulations on HPC
            log_dir: Directory for log files

        Returns:
            List of paths to generated script files
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        effective_log_dir = log_dir or self.config.log_dir
        if not effective_log_dir:
            raise ValueError("HPC log_dir is required for SLURM script generation.")
        if not self.config.modules:
            raise ValueError("HPC modules list is empty. Set hpc.modules in settings.")
        if self.config.use_tmpdir and not self.config.scratch_dir:
            raise ValueError("HPC scratch_dir is required when use_tmpdir is true.")

        n_sims = len(simulation_paths)
        n_scripts = math.ceil(n_sims / self.config.max_array_size)

        scripts = []
        template = self.jinja_env.get_template('slurm_array.j2')

        for i in range(n_scripts):
            start_idx = i * self.config.max_array_size
            end_idx = min((i + 1) * self.config.max_array_size, n_sims)
            chunk = simulation_paths[start_idx:end_idx]

            manifest_name = f"manifest_{i+1}.txt"
            manifest_path = output_dir / manifest_name
            manifest_path.write_text('\n'.join(chunk))

            manifest_rel = f"{base_dir}/{output_dir.name}/{manifest_name}"
            context = self.config.to_dict()
            context.update({
                'array_size': len(chunk),
                'manifest_file': manifest_rel,
                'base_dir': base_dir,
                'log_dir': effective_log_dir,
            })

            if n_scripts > 1:
                context['job_name'] = f"{self.config.job_name}_{i+1}"

            script_content = template.render(context)
            script_name = f"run_{i+1}.sh" if n_scripts > 1 else "run.sh"
            script_path = output_dir / script_name
            script_path.write_text(script_content)
            scripts.append(script_path)

        self._write_master_script(output_dir, scripts, 'slurm')

        return scripts

    def _write_master_script(
            self,
            output_dir: Path,
            scripts: List[Path],
            scheduler: Literal['pbs', 'slurm']) -> Path:
        """Write a master instruction file to submit all job arrays.

        Args:
            output_dir: Directory to write script to
            scripts: List of generated script paths
            scheduler: Scheduler type ('pbs' or 'slurm')

        Returns:
            Path to master script
        """
        submit_cmd = 'qsub' if scheduler == 'pbs' else 'sbatch'

        sim_root = output_dir.parent
        sim_dir_name = sim_root.name
        hpc_home = self.config.hpc_home or "<HPC_HOME>/"
        lines = [
            '# Submit all job arrays',
            '',
            '# Optional: upload simulations to HPC',
            f'# rsync -rvltoD {sim_dir_name} {hpc_home}',
            '',
            '# Optional: download results (and visuals) from HPC',
            f'# rsync -avzhP --include="*/" --include="results/***" --include="visuals/***" --exclude="*" {hpc_home}{sim_dir_name} ./{sim_dir_name}',
            '',
        ]
        lines.append(f'cd {sim_root}')
        lines.append('')
        for script in scripts:
            lines.append(f'{submit_cmd} {output_dir.name}/{script.name}')

        master_path = output_dir / 'submit_all.txt'
        master_path.write_text('\n'.join(lines))

        return master_path

    def generate_scripts(
            self,
            simulation_paths: List[str],
            output_dir: Path,
            scheduler: Literal['pbs', 'slurm'] = 'pbs',
            **kwargs) -> List[Path]:
        """Generate HPC scripts for the specified scheduler.

        Args:
            simulation_paths: List of relative paths to simulation directories
            output_dir: Directory to write scripts to
            scheduler: Scheduler type ('pbs' or 'slurm')
            **kwargs: Additional arguments passed to the specific generator

        Returns:
            List of paths to generated script files
        """
        if scheduler == 'pbs':
            return self.generate_pbs_scripts(
                simulation_paths, output_dir, **kwargs
            )
        if scheduler == 'slurm':
            return self.generate_slurm_scripts(
                simulation_paths, output_dir, **kwargs
            )
        raise ValueError(
            f"Unknown scheduler: {scheduler}. Use 'pbs' or 'slurm'."
        )


def create_hpc_package(
        simulation_dir: Path,
        output_dir: Path,
        scheduler: Literal['pbs', 'slurm'] = 'pbs',
        config: Optional[HPCConfig] = None) -> Path:
    """Create a complete HPC package ready for transfer.

    This function creates a self-contained directory with all simulation
    files, HPC scripts, and manifests needed to run on an HPC cluster.

    Args:
        simulation_dir: Directory containing FrictionSim2D output
        output_dir: Directory to create the package in
        scheduler: HPC scheduler type
        config: HPC configuration

    Returns:
        Path to the created package directory
    """
    simulation_dir = Path(simulation_dir)
    output_dir = Path(output_dir)

    package_dir = output_dir / "friction2d_package"
    package_dir.mkdir(parents=True, exist_ok=True)

    simulation_paths = []
    for lammps_dir in simulation_dir.rglob('lammps'):
        if lammps_dir.is_dir():
            rel_path = lammps_dir.parent.relative_to(simulation_dir)
            simulation_paths.append(str(rel_path))

    if not simulation_paths:
        raise ValueError(f"No simulation directories found in {simulation_dir}")

    sims_dir = package_dir / 'simulations'
    shutil.copytree(
        simulation_dir,
        sims_dir,
        ignore=shutil.ignore_patterns('*.lammpstrj')
    )

    scripts_dir = package_dir / 'scripts'
    generator = HPCScriptGenerator(config)
    generator.generate_scripts(
        simulation_paths,
        scripts_dir,
        scheduler=scheduler,
        base_dir='../simulations'
    )

    info = {
        'n_simulations': len(simulation_paths),
        'scheduler': scheduler,
        'created_from': str(simulation_dir),
    }

    (package_dir / 'package_info.json').write_text(json.dumps(info, indent=2))

    readme = f"""# FrictionSim2D HPC Package

This package contains {len(simulation_paths)} simulations ready for HPC execution.

## Contents
- `simulations/`: All LAMMPS input files
- `scripts/`: HPC submission scripts ({scheduler.upper()})
- `package_info.json`: Package metadata

## Usage
1. Transfer this entire directory to your HPC cluster
2. Navigate to the `scripts/` directory
3. Follow `submit_all.txt` to submit all jobs
4. Monitor job status with `{'qstat' if scheduler == 'pbs' else 'squeue'}`
5. After completion, transfer results back

## Scheduler: {scheduler.upper()}
"""
    (package_dir / 'README.md').write_text(readme)

    return package_dir
