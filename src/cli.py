"""Command Line Interface for FrictionSim2D.

Handles simulation execution, parameter sweeps, and settings management.
"""

import argparse
import logging
import sys
import shutil
import itertools
from pathlib import Path
from copy import deepcopy
from typing import List, Dict, Any
from importlib import resources
import yaml

from src.core.config import (
    parse_config, AFMSimulationConfig, SheetOnSheetSimulationConfig, 
    load_settings)
from src.builders.afm import AFMSimulation
from src.builders.sheetonsheet import SheetOnSheetSimulation

# Configure logging
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

def handle_settings(args):
    """Handle 'settings' subcommand."""
    if args.action == 'show':
        defaults = load_settings()
        print(yaml.dump(defaults.dict(), default_flow_style=False))
    elif args.action == 'reset':
        local_settings = Path("settings.yaml")
        if local_settings.exists():
            local_settings.unlink()
            logger.info("Removed local settings.yaml. Using package defaults.")
        else:
            logger.info("No local settings found to reset.")
    elif args.action == 'init':
        with resources.as_file(resources.files('src.data.settings') / 'settings_default.yaml') as p:
            shutil.copy(p, "settings.yaml")
        logger.info("Created mutable 'settings.yaml' in current directory.")

def handle_run(args):
    """Handle 'run' subcommand."""
    config_path = Path(args.config_file)
    if not config_path.exists():
        logger.error("Config file not found: %s", config_path)
        sys.exit(1)

    base_dict = parse_config(config_path)
    defaults = load_settings()
    configs_to_run = expand_config_sweeps(base_dict)

    logger.info("Found %d simulation configurations to run.", len(configs_to_run))

    for i, run_dict in enumerate(configs_to_run):
        run_dict['settings'] = defaults.dict()

        mat = run_dict['2D'].get('mat', 'unknown')
        x = run_dict['2D'].get('x', 100)
        y = run_dict['2D'].get('y', 100)
        temp = run_dict['general'].get('temp', 300)

        if args.model == 'afm':
            tip_mat = run_dict.get('tip', {}).get('mat', 'Si')
            tip_amorph = run_dict.get('tip', {}).get('amorph', 'c')
            tip_r = run_dict.get('tip', {}).get('r', 25)
            sub_mat = run_dict.get('sub', {}).get('mat', 'Si')
            sub_amorph = run_dict.get('sub', {}).get('amorph', 'a')

            sub_str = f"{sub_amorph}{sub_mat}" if sub_amorph == 'a' else sub_mat
            tip_str = f"{tip_amorph}{tip_mat}" if tip_amorph == 'a' else tip_mat

            run_output_dir = (
                Path(args.output_dir) / "afm" / mat / f"{x}x_{y}y" /
                f"sub_{sub_str}_tip_{tip_str}_r{int(tip_r)}" /
                f"K{int(temp)}"
            )
        else:
            run_output_dir = (
                Path(args.output_dir) / "sheetonsheet" / mat / f"{x}x_{y}y" /
                f"K{int(temp)}"
            )

        logger.info("--- Run %d/%d: %s ---", i+1, len(configs_to_run), run_output_dir)

        prov_dir = run_output_dir / 'provenance'
        prov_dir.mkdir(parents=True, exist_ok=True)

        try:
            if args.model == 'afm':
                config_obj = AFMSimulationConfig(**run_dict)
                per_run_config_path = prov_dir / 'config.json'
                per_run_config_path.write_text(config_obj.model_dump_json(indent=2), encoding='utf-8')
                builder = AFMSimulation(config_obj, str(run_output_dir), config_path=str(per_run_config_path))
            else:
                config_obj = SheetOnSheetSimulationConfig(**run_dict)
                per_run_config_path = prov_dir / 'config.json'
                per_run_config_path.write_text(config_obj.model_dump_json(indent=2), encoding='utf-8')
                builder = SheetOnSheetSimulation(config_obj, str(run_output_dir), config_path=str(per_run_config_path))

            builder.build()

        except Exception as e:  # pylint: disable=broad-except
            logger.error("Run %d failed: %s", i+1, e)
            continue

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="FrictionSim2D CLI")
    subparsers = parser.add_subparsers(dest='command', required=True)

    run_parser = subparsers.add_parser('run', help='Run simulations')
    run_parser.add_argument("config_file", type=str)
    run_parser.add_argument("--model", "-m", choices=['afm', 'sheetonsheet'], default='afm')
    run_parser.add_argument("--output-dir", "-o", default="simulation_output")
    run_parser.set_defaults(func=handle_run)

    settings_parser = subparsers.add_parser('settings', help='Manage settings')
    settings_parser.add_argument("action", choices=['show', 'init', 'reset'])
    settings_parser.set_defaults(func=handle_settings)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
