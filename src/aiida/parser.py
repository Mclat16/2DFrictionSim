"""AiiDA parser for FrictionSim2D LAMMPS CalcJobs."""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

from aiida import orm
from aiida.parsers.parser import Parser


class LammpsFrictionParser(Parser):
    """Parse retrieved outputs for FrictionSim2D LAMMPS runs."""

    def parse(self, **kwargs):  # type: ignore[override]
        retrieved = self.retrieved
        if retrieved is None:
            return self.exit_codes.ERROR_NO_RESULTS

        repo = retrieved.base.repository
        names = repo.list_object_names()

        has_results = any(
            '/results/' in name or name.startswith('results/') or name.startswith('friction_')
            for name in names
        )
        has_visuals = any(
            '/visuals/' in name or name.startswith('visuals/') or name.endswith('.lammpstrj')
            for name in names
        )
        stdout_names = [name for name in names if name.endswith('.out')]
        has_log = 'log.lammps' in names
        if not has_results and not has_visuals and not stdout_names and not has_log:
            return self.exit_codes.ERROR_NO_RESULTS

        results_folder = orm.FolderData()
        for name in names:
            if (
                name.startswith('results/')
                or name.startswith('visuals/')
                or name.startswith('friction_')
                or name.endswith('.lammpstrj')
                or '/results/' in name
                or '/visuals/' in name
            ):
                with repo.open(name, 'rb') as handle:
                    results_folder.base.repository.put_object_from_filelike(handle, name)
        results_folder.store()
        self.out('results_folder', results_folder)

        if 'log.lammps' in names:
            with repo.open('log.lammps', 'rb') as handle:
                with NamedTemporaryFile(prefix='lammps_log_', suffix='.log', delete=True) as tmp:
                    tmp.write(handle.read())
                    tmp.flush()
                    log_file = orm.SinglefileData(file=tmp.name)
            log_file.store()
            self.out('log_file', log_file)

        if stdout_names:
            stdout_folder = orm.FolderData()
            for name in stdout_names:
                with repo.open(name, 'rb') as handle:
                    stdout_folder.base.repository.put_object_from_filelike(handle, name)
            stdout_folder.store()
            self.out('stdout_folder', stdout_folder)

        params = getattr(self.node.inputs, 'parameters', None)
        if params is not None:
            local_sim_dir = params.get_dict().get('local_sim_dir')
            if local_sim_dir:
                _copy_outputs_to_local(repo, names, Path(local_sim_dir))

        if not has_results and not has_visuals:
            return self.exit_codes.ERROR_LAMMPS_FAILED

        return None


def _copy_outputs_to_local(repo, names, local_sim_dir: Path) -> None:
    """Copy results and visuals into the local simulation directory."""
    results_dir = local_sim_dir / 'results'
    visuals_dir = local_sim_dir / 'visuals'
    results_dir.mkdir(parents=True, exist_ok=True)
    visuals_dir.mkdir(parents=True, exist_ok=True)

    for kind, rel_name, repo_name in _iter_output_files(names):
        target_dir = results_dir if kind == 'results' else visuals_dir
        target_path = target_dir / rel_name
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with repo.open(repo_name, 'rb') as handle:
            target_path.write_bytes(handle.read())


def _iter_output_files(names):
    """Yield tuples of (kind, rel_name, repo_name) for output files."""
    for name in names:
        if '/results/' in name:
            yield 'results', name.split('/results/', 1)[1], name
        elif name.startswith('results/'):
            yield 'results', name.split('results/', 1)[1], name
        elif name.startswith('friction_'):
            yield 'results', name, name
        elif '/visuals/' in name:
            yield 'visuals', name.split('/visuals/', 1)[1], name
        elif name.startswith('visuals/'):
            yield 'visuals', name.split('visuals/', 1)[1], name
        elif name.endswith('.lammpstrj'):
            yield 'visuals', name, name
