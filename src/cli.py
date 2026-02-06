"""Command Line Interface for FrictionSim2D.

Unified CLI for simulation execution, HPC script generation, and AiiDA integration.
"""

import logging
import sys
import shutil
import itertools
from pathlib import Path
from copy import deepcopy
from typing import List, Dict, Any, Optional
from importlib import resources
import yaml
import click

from src.core.config import (
    parse_config, AFMSimulationConfig, SheetOnSheetSimulationConfig, 
    load_settings)
from src.builders.afm import AFMSimulation
from src.builders.sheetonsheet import SheetOnSheetSimulation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def expand_config_sweeps(base_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Expand config with material lists and parameter sweeps.

    Args:
        base_config: Base configuration dictionary.

    Returns:
        List of expanded single-run configurations.
    """
    sweep_params = {}

    def resolve_materials_list(section_config: Dict[str, Any]) -> List[str]:
        """Read materials_list file if present."""
        if 'materials_list' not in section_config:
            return []

        mat_list_path = section_config.get('materials_list', '')
        if isinstance(mat_list_path, str) and mat_list_path.endswith(".txt"):
            path = Path(mat_list_path)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    return [line.strip() for line in f if line.strip()]
            logger.warning("Material list file %s not found.", path)
        return []

    def expand_mat_template(section_config: Dict[str, Any], mat_value: str) -> Dict[str, Any]:
        """Replace {mat} placeholders with material name."""
        expanded = {}
        for key, val in section_config.items():
            if key == 'materials_list':
                continue
            if isinstance(val, str) and '{mat}' in val:
                expanded[key] = val.replace('{mat}', mat_value)
            else:
                expanded[key] = val
        return expanded

    if '2D' in base_config:
        materials = resolve_materials_list(base_config['2D'])
        if materials:
            sweep_params[('2D', '_material_expand')] = materials

    lammps_loop_params = {'force', 'scan_angle', 'pressure', 'scan_speed'}

    if 'general' in base_config:
        for key, val in base_config['general'].items():
            if isinstance(val, list) and key not in lammps_loop_params:
                sweep_params[('general', key)] = val

    if not sweep_params:
        return [base_config]

    keys, values = zip(*sweep_params.items())
    permutations = [dict(zip(keys, v)) for v in itertools.product(*values)]

    expanded_configs = []
    for perm in permutations:
        new_conf = deepcopy(base_config)

        mat_value = perm.pop(('2D', '_material_expand'), None)
        if mat_value and '2D' in new_conf:
            new_conf['2D'] = expand_mat_template(new_conf['2D'], mat_value)

        for (section, key), val in perm.items():
            new_conf[section][key] = val

        expanded_configs.append(new_conf)

    return expanded_configs

# =============================================================================
# MAIN CLI GROUP
# =============================================================================

@click.group()
@click.version_option(version='0.1.0', prog_name='FrictionSim2D')
def cli():
    """FrictionSim2D - Generate LAMMPS input files for 2D material friction simulations."""
    pass

# =============================================================================
# RUN COMMANDS
# =============================================================================

@cli.group('run')
def run_group():
    """Run friction simulations."""
    pass

@run_group.command('afm')
@click.argument('config_file', type=click.Path(exists=True))
@click.option('--output-dir', '-o', default='simulation_output',
              help='Output directory for generated files')
@click.option('--aiida', 'use_aiida', is_flag=True,
              help='Enable AiiDA provenance tracking')
@click.option('--hpc', 'hpc_name', type=str, default=None,
              help='HPC configuration name (overrides settings)')
@click.option('--local', 'run_local', is_flag=True,
              help='Mark as local run (no HPC submission)')
def run_afm(config_file: str, output_dir: str, use_aiida: bool, 
            hpc_name: Optional[str], run_local: bool):
    """Generate AFM simulation files.
    
    Creates all necessary LAMMPS input files, structures, and potentials
    for tip-on-substrate friction simulations.
    
    Example:
        FrictionSim2D run.afm afm_config.ini -o ./afm_output --aiida
    """
    _run_simulation('afm', config_file, output_dir, use_aiida, hpc_name, run_local)

@run_group.command('sheetonsheet')
@click.argument('config_file', type=click.Path(exists=True))
@click.option('--output-dir', '-o', default='simulation_output',
              help='Output directory for generated files')
@click.option('--aiida', 'use_aiida', is_flag=True,
              help='Enable AiiDA provenance tracking')
@click.option('--hpc', 'hpc_name', type=str, default=None,
              help='HPC configuration name (overrides settings)')
@click.option('--local', 'run_local', is_flag=True,
              help='Mark as local run (no HPC submission)')
def run_sheetonsheet(config_file: str, output_dir: str, use_aiida: bool,
                     hpc_name: Optional[str], run_local: bool):
    """Generate sheet-on-sheet simulation files.
    
    Creates all necessary LAMMPS input files for 4-layer sheet-on-sheet
    friction simulations.
    
    Example:
        FrictionSim2D run.sheetonsheet sheet_config.ini -o ./sheet_output
    """
    _run_simulation('sheetonsheet', config_file, output_dir, use_aiida, hpc_name, run_local)

def _run_simulation(model: str, config_file: str, output_dir: str,
                   use_aiida: bool, hpc_name: Optional[str], run_local: bool):
    """Internal function to run simulations."""
    config_path = Path(config_file)
    
    if use_aiida:
        from src.aiida import AIIDA_AVAILABLE
        if not AIIDA_AVAILABLE:
            click.echo("⚠️  AiiDA not available. Install with:", err=True)
            click.echo("   conda install -c conda-forge aiida-core", err=True)
            raise click.Abort()
    
    base_dict = parse_config(config_path)
    defaults = load_settings()
    
    if use_aiida:
        defaults.aiida.enabled = True
        defaults.aiida.create_provenance = True
    
    configs_to_run = expand_config_sweeps(base_dict)
    
    click.echo(f"📋 Found {len(configs_to_run)} simulation configurations")
    
    created_simulations = []
    
    for i, run_dict in enumerate(configs_to_run):
        run_dict['settings'] = defaults.dict()
        
        mat = run_dict['2D'].get('mat', 'unknown')
        x = run_dict['2D'].get('x', 100)
        y = run_dict['2D'].get('y', 100)
        temp = run_dict['general'].get('temp', 300)
        
        if model == 'afm':
            tip_mat = run_dict.get('tip', {}).get('mat', 'Si')
            tip_amorph = run_dict.get('tip', {}).get('amorph', 'c')
            tip_r = run_dict.get('tip', {}).get('r', 25)
            sub_mat = run_dict.get('sub', {}).get('mat', 'Si')
            sub_amorph = run_dict.get('sub', {}).get('amorph', 'a')
            
            sub_str = f"{sub_amorph}{sub_mat}" if sub_amorph == 'a' else sub_mat
            tip_str = f"{tip_amorph}{tip_mat}" if tip_amorph == 'a' else tip_mat
            
            run_output_dir = (
                Path(output_dir) / "afm" / mat / f"{x}x_{y}y" /
                f"sub_{sub_str}_tip_{tip_str}_r{int(tip_r)}" / f"K{int(temp)}"
            )
        else:
            run_output_dir = (
                Path(output_dir) / "sheetonsheet" / mat / f"{x}x_{y}y" / f"K{int(temp)}"
            )
        
        click.echo(f"\n🔧 [{i+1}/{len(configs_to_run)}] Building: {run_output_dir.name}")
        
        prov_dir = run_output_dir / 'provenance'
        prov_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            if model == 'afm':
                config_obj = AFMSimulationConfig(**run_dict)
                per_run_config_path = prov_dir / 'config.json'
                per_run_config_path.write_text(config_obj.model_dump_json(indent=2), encoding='utf-8')
                builder = AFMSimulation(config_obj, str(run_output_dir), 
                                       config_path=str(per_run_config_path))
            else:
                config_obj = SheetOnSheetSimulationConfig(**run_dict)
                per_run_config_path = prov_dir / 'config.json'
                per_run_config_path.write_text(config_obj.model_dump_json(indent=2), encoding='utf-8')
                builder = SheetOnSheetSimulation(config_obj, str(run_output_dir),
                                                config_path=str(per_run_config_path))
            
            builder.build()
            created_simulations.append(run_output_dir)
            click.echo(f"   ✅ Complete")
            
        except Exception as e:
            click.echo(f"   ❌ Failed: {e}", err=True)
            logger.exception("Build failed")
            continue
    
    if created_simulations and use_aiida:
        click.echo(f"\n📦 Registering {len(created_simulations)} simulations in AiiDA...")
        _register_simulations_aiida(created_simulations, config_path)
    
    click.echo(f"\n✅ Generation complete: {len(created_simulations)}/{len(configs_to_run)} successful")
    click.echo(f"📂 Output directory: {Path(output_dir).absolute()}")

def _register_simulations_aiida(simulation_dirs: List[Path], config_path: Path):
    """Register generated simulations with AiiDA."""
    try:
        from src.aiida.integration import register_simulation_batch
        registered = register_simulation_batch(simulation_dirs, config_path)
        click.echo(f"   ✅ Registered {len(registered)} simulations")
    except ImportError:
        click.echo("   ⚠️  AiiDA integration module not found", err=True)
    except Exception as e:
        click.echo(f"   ⚠️  Registration failed: {e}", err=True)
        logger.exception("AiiDA registration failed")

# =============================================================================
# SETTINGS COMMANDS
# =============================================================================

@cli.group('settings')
def settings_group():
    """Manage simulation settings."""
    pass

@settings_group.command('show')
def settings_show():
    """Display current settings."""
    defaults = load_settings()
    click.echo(yaml.dump(defaults.dict(), default_flow_style=False))

@settings_group.command('init')
def settings_init():
    """Create a local settings.yaml file for customization."""
    with resources.as_file(resources.files('src.data.settings') / 'settings.yaml') as p:
        shutil.copy(p, "settings.yaml")
    click.echo("✅ Created 'settings.yaml' in current directory")

@settings_group.command('reset')
def settings_reset():
    """Remove local settings.yaml and use package defaults."""
    local_settings = Path("settings.yaml")
    if local_settings.exists():
        local_settings.unlink()
        click.echo("✅ Removed local settings.yaml")
    else:
        click.echo("ℹ️  No local settings found")

# =============================================================================
# HPC COMMANDS
# =============================================================================

@cli.group('hpc')
def hpc_group():
    """Generate HPC submission scripts."""
    pass

@hpc_group.command('generate')
@click.argument('simulation_dir', type=click.Path(exists=True))
@click.option('--scheduler', '-s', type=click.Choice(['pbs', 'slurm']), default='pbs',
              help='HPC scheduler type')
@click.option('--output-dir', '-o', default=None,
              help='Output directory for scripts (default: simulation_dir/hpc)')
def hpc_generate(simulation_dir: str, scheduler: str, output_dir: Optional[str]):
    """Generate HPC submission scripts for existing simulations.
    
    Scans simulation directory and creates PBS or SLURM job scripts.
    
    Example:
        FrictionSim2D hpc generate ./afm_output --scheduler pbs
    """
    from src.hpc import HPCScriptGenerator, HPCConfig
    
    sim_dir = Path(simulation_dir)
    out_dir = Path(output_dir) if output_dir else sim_dir / 'hpc'
    out_dir.mkdir(parents=True, exist_ok=True)
    
    click.echo(f"🖥️  Generating {scheduler.upper()} scripts for: {sim_dir}")
    
    simulation_paths = []
    for lammps_dir in sim_dir.rglob('lammps'):
        if lammps_dir.is_dir() and (lammps_dir / 'system.in').exists():
            rel_path = lammps_dir.parent.relative_to(sim_dir)
            simulation_paths.append(str(rel_path))
    
    if not simulation_paths:
        click.echo("❌ No simulation directories found", err=True)
        raise click.Abort()
    
    click.echo(f"📋 Found {len(simulation_paths)} simulations")
    
    settings = load_settings()
    hpc_config = HPCConfig.from_settings(settings.hpc)
    hpc_config.scheduler_type = scheduler
    
    generator = HPCScriptGenerator(hpc_config)
    scripts = generator.generate_scripts(
        simulation_paths=simulation_paths,
        output_dir=out_dir,
        scheduler=scheduler
    )
    
    click.echo(f"✅ Generated {len(scripts)} script(s) in {out_dir}")
    click.echo(f"\n📝 Next steps:")
    click.echo(f"   1. Review scripts in {out_dir}")
    click.echo(f"   2. Transfer to HPC cluster")
    click.echo(f"   3. Run ./submit_all.sh")

# =============================================================================
# AIIDA COMMANDS (Optional)
# =============================================================================

@cli.group('aiida')
def aiida_group():
    """AiiDA workflow management (requires aiida-core)."""
    from src.aiida import AIIDA_AVAILABLE
    if not AIIDA_AVAILABLE:
        click.echo("⚠️  AiiDA not available. Install with:", err=True)
        click.echo("   conda install -c conda-forge aiida-core", err=True)
        raise click.Abort()

@aiida_group.command('status')
def aiida_status():
    """Check AiiDA installation and profile status."""
    from src.aiida import AIIDA_AVAILABLE
    
    if not AIIDA_AVAILABLE:
        click.echo("❌ AiiDA not installed")
        return
    
    click.echo("✅ AiiDA is installed")
    
    try:
        from aiida import load_profile
        profile = load_profile()
        click.echo(f"✅ Active profile: {profile.name}")
        click.echo(f"   Storage: {profile.storage_backend}")
    except Exception as e:
        click.echo(f"⚠️  No active profile: {e}")
        click.echo("\n📝 Setup AiiDA with: verdi presto --use-postgres")

@aiida_group.command('import')
@click.argument('results_dir', type=click.Path(exists=True))
@click.option('--process/--no-process', default=True,
              help='Run postprocessing on results')
def aiida_import(results_dir: str, process: bool):
    """Import completed simulation results into AiiDA database.
    
    Example:
        FrictionSim2D aiida import ./returned_results
    """
    from src.aiida.integration import import_results_to_aiida
    
    results_path = Path(results_dir)
    click.echo(f"📥 Importing results from: {results_path}")
    
    try:
        if process:
            click.echo("🔄 Running postprocessing...")
            from src.postprocessing.read_data import DataReader
            reader = DataReader(results_dir=str(results_path))
            click.echo("   ✅ Postprocessing complete")
        
        imported = import_results_to_aiida(results_path)
        click.echo(f"✅ Imported {len(imported)} simulations to AiiDA")
        
    except Exception as e:
        click.echo(f"❌ Import failed: {e}", err=True)
        logger.exception("Import failed")
        raise click.Abort()

@aiida_group.command('query')
@click.option('--material', '-m', help='Filter by material')
@click.option('--layers', '-l', type=int, help='Filter by layer count')
@click.option('--force', '-f', type=float, help='Filter by applied force')
@click.option('--format', 'output_format', type=click.Choice(['table', 'csv', 'json']),
              default='table', help='Output format')
@click.option('--output', '-o', type=click.Path(), help='Save to file')
def aiida_query(material: Optional[str], layers: Optional[int], force: Optional[float],
                output_format: str, output: Optional[str]):
    """Query simulation database.
    
    Example:
        FrictionSim2D aiida query --material h-MoS2 --layers 2 --format csv
    """
    from src.aiida.db import Friction2DDB
    
    db = Friction2DDB()
    
    filters = {}
    if material:
        filters['material'] = material
    if layers:
        filters['layers'] = layers
    if force:
        filters['force'] = force
    
    click.echo(f"🔍 Querying database with filters: {filters}")
    
    try:
        results = db.query(**filters)
        click.echo(f"📊 Found {results.total_count} results")
        
        if output_format == 'table':
            df = results.to_dataframe()
            click.echo("\n" + df.to_string(index=False))
        elif output_format == 'csv':
            df = results.to_dataframe()
            if output:
                df.to_csv(output, index=False)
                click.echo(f"✅ Saved to {output}")
            else:
                click.echo(df.to_csv(index=False))
        elif output_format == 'json':
            if output:
                results.export_json(Path(output))
                click.echo(f"✅ Saved to {output}")
            else:
                import json
                click.echo(json.dumps(results.query_params, indent=2))
                
    except Exception as e:
        click.echo(f"❌ Query failed: {e}", err=True)
        raise click.Abort()

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """Main CLI entry point."""
    try:
        cli()
    except Exception as e:
        logger.exception("Command failed")
        sys.exit(1)

if __name__ == "__main__":
    main()

