"""Postprocessing and visualization for friction simulation results.

This package provides tools for reading, analyzing, and visualizing the
output from friction simulations:
    - DataReader: Reads and parses simulation output files
    - Plotter: Generates plots and figures from processed data
"""

from src.postprocessing.read_data import DataReader
from src.postprocessing.plot_data import Plotter

__all__ = [
    'DataReader',
    'Plotter',
]
