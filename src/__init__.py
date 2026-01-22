"""FrictionSim2D - Framework for 2D material friction simulations.

Provides LAMMPS-based molecular dynamics setup for AFM and sheet-on-sheet
friction simulations with automatic potential generation.
"""

__version__ = "0.2.0"

from pathlib import Path
import logging

from src.cli import expand_config_sweeps
from src.builders.afm import AFMSimulation
from src.builders.sheetonsheet import SheetOnSheetSimulation
from src.core.potential_manager import PotentialManager
from src.core.config import (
    AFMSimulationConfig,
    SheetOnSheetSimulationConfig,
    load_settings,
    parse_config,
)

logger = logging.getLogger(__name__)


def afm(config_file: str = "afm_config.ini"):
    """Run AFM simulations from config file.

    Args:
        config_file: Path to .ini configuration file.
    """
    _run_all(config_file, model="afm")


def sheetonsheet(config_file: str = "sheet_config.ini"):
    """Run sheet-on-sheet simulations from config file.

    Args:
        config_file: Path to .ini configuration file.
    """
    _run_all(config_file, model="sheetonsheet")


def _run_all(config_file: str, model: str = "afm"):
    """Run all simulations defined in config file.

    Args:
        config_file: Path to .ini config file.
        model: Simulation type ('afm' or 'sheetonsheet').
    """

    config_path = Path(config_file)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    base_dict = parse_config(config_path)
    defaults = load_settings()
    configs_to_run = expand_config_sweeps(base_dict)

    print(f"Found {len(configs_to_run)} simulation configurations to run.")

    for i, run_dict in enumerate(configs_to_run):
        run_dict['settings'] = defaults.dict()

        mat = run_dict['2D'].get('mat', 'unknown')
        x = run_dict['2D'].get('x', 100)
        y = run_dict['2D'].get('y', 100)
        temp = run_dict['general'].get('temp', 300)

        if model == "afm":
            tip_mat = run_dict.get('tip', {}).get('mat', 'Si')
            tip_amorph = run_dict.get('tip', {}).get('amorph', 'c')
            tip_r = run_dict.get('tip', {}).get('r', 25)
            sub_mat = run_dict.get('sub', {}).get('mat', 'Si')
            sub_amorph = run_dict.get('sub', {}).get('amorph', 'a')

            sub_str = f"{sub_amorph}{sub_mat}" if sub_amorph == 'a' else sub_mat
            tip_str = f"{tip_amorph}{tip_mat}" if tip_amorph == 'a' else tip_mat

            output_dir = (
                Path("afm") / mat / f"{x}x_{y}y" /
                f"sub_{sub_str}_tip_{tip_str}_r{int(tip_r)}" /
                f"K{int(temp)}"
            )
        else:
            output_dir = (
                Path("sheetonsheet") / mat / f"{x}x_{y}y" /
                f"K{int(temp)}"
            )

        print(f"--- Run {i+1}/{len(configs_to_run)}: {output_dir} ---")

        prov_dir = output_dir / 'provenance'
        prov_dir.mkdir(parents=True, exist_ok=True)

        try:
            if model == 'afm':
                config_obj = AFMSimulationConfig(**run_dict)
                config_json_path = prov_dir / 'config.json'
                config_json_path.write_text(config_obj.model_dump_json(indent=2), encoding='utf-8')
                builder = AFMSimulation(config_obj, output_dir, config_path=str(config_json_path))
            else:
                config_obj = SheetOnSheetSimulationConfig(**run_dict)
                config_json_path = prov_dir / 'config.json'
                config_json_path.write_text(config_obj.model_dump_json(indent=2), encoding='utf-8')
                builder = SheetOnSheetSimulation(config_obj, output_dir, config_path=str(config_json_path))

            builder.build()
            print(f"  -> Completed: {output_dir}")

        except Exception as e:  # pylint: disable=broad-except
            logger.error("Run %d failed: %s", i+1, e)
            print(f"  -> Failed: {e}")
            continue


__all__ = [
    "afm",
    "sheetonsheet",
    "AFMSimulation",
    "SheetOnSheetSimulation",
    "PotentialManager",
    "AFMSimulationConfig",
    "SheetOnSheetSimulationConfig",
    "load_settings",
    "parse_config",
]
