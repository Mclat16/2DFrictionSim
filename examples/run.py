#!/usr/bin/env python3
"""Simple runner script for FrictionSim2D.

This script provides a minimal interface to run AFM or SheetOnSheet simulations.
For full control, use the CLI directly:
    
    python -m FrictionSim2D run afm_config.ini -m afm -o output/
    
Or import and use the builders programmatically.
"""

import subprocess
import sys
from pathlib import Path


def run_afm(config_file: str = "afm_config.ini", output_dir: str = "simulation_output"):
    """Run AFM simulations from a config file.
    
    Args:
        config_file: Path to the .ini configuration file.
        output_dir: Base directory for simulation outputs.
    """
    cmd = [
        sys.executable, "-m", "FrictionSim2D",
        "run", config_file,
        "-m", "afm",
        "-o", output_dir
    ]
    subprocess.run(cmd, check=True)


def run_sheetonsheet(config_file: str = "sheet_config.ini", output_dir: str = "simulation_output"):
    """Run SheetOnSheet simulations from a config file.
    
    Args:
        config_file: Path to the .ini configuration file.
        output_dir: Base directory for simulation outputs.
    """
    cmd = [
        sys.executable, "-m", "FrictionSim2D",
        "run", config_file,
        "-m", "sheetonsheet",
        "-o", output_dir
    ]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    # Default: run AFM simulation with config in current directory
    config_path = Path("afm_config.ini")
    
    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        print("Usage: python run.py")
        print("       (expects afm_config.ini in current directory)")
        print("\nOr use CLI directly:")
        print("  python -m FrictionSim2D run <config.ini> -m afm -o output/")
        sys.exit(1)
    
    run_afm(str(config_path))
