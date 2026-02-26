"""Plotting and visualization for friction simulation results.

Generates configurable plots from processed simulation data exported
by :class:`~src.postprocessing.read_data.DataReader`.  Supports summary
plots, time-series, scatter comparisons, correlation heatmaps and
friction-ranking exports.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# MATLAB gem12 colour palette (12 distinct colours for line plots)
GEM12_COLORS = [
    '#0072BD', '#D95319', '#EDB120', '#7E2F8E', '#77AC30', '#4DBEEE',
    '#A2142F', '#FFD60A', '#6582FD', '#FF453A', '#00A3A3', '#CB845D',
]

DEFAULT_SETTINGS: dict[str, Any] = {
    "figure": {"size": [10, 7], "dpi": 150},
    "fonts": {
        "title": 26, "axis_label": 24,
        "tick_label": 22, "legend": 16,
    },
    "colors": {"palette": "gem12"},
    "markers": {"style": "o", "size": 12},
    "lines": {"width": 1.3, "fit_style": "--", "fit_alpha": 0.8},
    "grid": {
        "show": True, "which": "both",
        "major_style": "-", "minor_style": ":",
        "major_alpha": 0.5, "minor_alpha": 0.3,
    },
    "error_bands": {"alpha": 0.2},
    "legend": {"location": "best"},
    "layout": {},
    "axes": {"use_scientific_notation": True, "scilimits": [-3, 4]},
    "export": {"formats": ["png"], "transparent": False},
}


# =========================================================================
# PLOTTER CLASS
# =========================================================================

class Plotter:
    """Generate plots from friction simulation data."""

    def __init__(
        self,
        data_dirs: list[str],
        labels: list[str],
        output_dir: str,
        settings: dict | None = None,
    ) -> None:
        self.data_dirs = data_dirs
        self.labels = labels
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.settings = DEFAULT_SETTINGS.copy()
        if settings:
            self._deep_merge_dict(self.settings, settings)

        self.figure_size = tuple(self.settings["figure"]["size"])
        self.time_step_fs = 1.0

        self.full_data_files: dict[str, dict] = {
            label: {} for label in self.labels
        }
        self.metadata: dict = {}
        self.summary_df_cache: pd.DataFrame | None = None
        self.material_type_map: dict[str, str] = {}

        self.type_display_names = {
            'b_type': 'buckled',
            'h_type': 'hexagonal',
            't_type': 'trigonal',
            'p_type': 'puckered',
            'other': 'bi-buckled',
        }

        self._discover_data_files()
        self._load_all_metadata()
        self._create_material_type_map()

    # =====================================================================
    # INITIALISATION HELPERS
    # =====================================================================

    def _deep_merge_dict(self, d1: dict, d2: dict) -> None:
        """Recursively merge *d2* into *d1*."""
        for k, v in d2.items():
            if k in d1 and isinstance(d1[k], dict) and isinstance(v, dict):
                self._deep_merge_dict(d1[k], v)
            elif k in d1 and isinstance(d1[k], list) and isinstance(v, list):
                d1[k].extend(v)
            else:
                d1[k] = v

    def _create_material_type_map(self) -> None:
        """Create a map from material_id to material_type from metadata."""
        material_types_dict = self.metadata.get('material_types')
        if isinstance(material_types_dict, dict):
            self.material_type_map = {
                material_id.strip(): type_name.strip()
                for type_name, material_list in material_types_dict.items()
                for material_id in material_list
            }
        else:
            logger.warning(
                "'material_types' not found in metadata. "
                "Plotting by type may fail."
            )

    def _discover_data_files(self) -> None:
        """Find all ``output_full_*.json`` files in each data directory."""
        for label, data_dir in zip(self.labels, self.data_dirs):
            search_dir = Path(data_dir) / 'outputs'

            if not search_dir.is_dir():
                logger.debug(
                    "'outputs' not found in %s, searching base directory.",
                    data_dir,
                )
                search_dir = Path(data_dir)

            if not search_dir.is_dir():
                logger.error(
                    "Data directory not found for label '%s': %s",
                    label, data_dir,
                )
                continue

            for entry in search_dir.iterdir():
                match = re.match(r'output_full_(.+)\.json', entry.name)
                if match:
                    file_key = match.group(1)
                    self.full_data_files[label][file_key] = str(entry)

            if not self.full_data_files[label]:
                logger.warning(
                    "No 'output_full_*.json' files found for label '%s'",
                    label,
                )

    def _load_all_metadata(self) -> None:
        """Load and merge metadata from all available data files."""
        for label in self.labels:
            if not self.full_data_files[label]:
                continue
            for file_key in self.full_data_files[label]:
                _, metadata = self._load_full_data(label, file_key)
                if metadata:
                    self._deep_merge_dict(self.metadata, metadata)

    def _load_full_data(
        self, label: str, file_key: str,
    ) -> tuple[dict | None, dict | None]:
        """Load a single data file and return ``(results, metadata)``."""
        file_path = self.full_data_files.get(label, {}).get(file_key)
        if not file_path:
            logger.debug(
                "No data file for label '%s', file_key '%s'",
                label, file_key,
            )
            return None, None
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            return data.get('results', {}), data.get('metadata', {})
        except (IOError, json.JSONDecodeError) as e:
            logger.error("Loading data from %s: %s", file_path, e)
            return None, None

    # =====================================================================
    # DATA EXTRACTION
    # =====================================================================

    def _extract_all_runs(self, label: str, file_key: str):
        """Yield a dict for each simulation run found in the data file."""
        results, _ = self._load_full_data(label, file_key)
        if not results:
            return

        def process_level(data_dict, params_so_far):
            if 'columns' in data_dict and 'data' in data_dict:
                df = pd.DataFrame(
                    data_dict['data'], columns=data_dict['columns'],
                )
                df = self._add_derived_columns(df)
                run_data = params_so_far.copy()
                run_data['df'] = df
                yield run_data
                return

            for key, value in data_dict.items():
                if not isinstance(value, dict):
                    continue
                new_params = params_so_far.copy()
                if 'id' not in new_params:
                    new_params['id'] = key.strip()
                else:
                    match_prefix = re.match(
                        r'([a-zA-Z]+)(\d+\.?\d*)', key,
                    )
                    if match_prefix:
                        prefix, val_str = match_prefix.groups()
                        val = float(val_str)
                        param_map = {
                            'f': 'force', 'a': 'angle',
                            'r': 'tip_radius', 'l': 'layer',
                            's': 'speed', 'p': 'pressure',
                        }
                        if prefix in param_map:
                            new_params[param_map[prefix]] = val
                    if m := re.match(r'(\d+\.?\d*)nN', key):
                        new_params['force'] = float(m.group(1))
                    if m := re.match(r'(\d+\.?\d*)deg', key):
                        new_params['angle'] = float(m.group(1))
                yield from process_level(value, new_params)

        yield from process_level(results, {})

    def _add_derived_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add derived quantities to a DataFrame."""
        if 'lfx' in df.columns and 'lfy' in df.columns:
            df['lf'] = np.sqrt(df['lfx']**2 + df['lfy']**2)

        if 'lf' in df.columns and 'nf' in df.columns:
            df['cof'] = (
                np.abs(df['lf']) / np.abs(df['nf'])
            ).replace([np.inf, -np.inf], np.nan)

        if 'tipz' in df.columns and 'comz' in df.columns:
            df['tip_sep'] = df['tipz'] - df['comz']

        if 'tipx' in df.columns and len(df) > 0:
            df['tipx'] = df['tipx'] - df['tipx'].iloc[0]
        if 'tipy' in df.columns and len(df) > 0:
            df['tipy'] = df['tipy'] - df['tipy'].iloc[0]

        if 'tipx' in df.columns and 'tipy' in df.columns:
            df['tip_pos'] = np.sqrt(df['tipx']**2 + df['tipy']**2)

        if all(c in df.columns for c in ['tipx', 'tipy', 'time']):
            time_diff_s = (
                df['time'].diff() * self.time_step_fs * 1e-15
            ).fillna(0)
            dist_diff_A = np.sqrt(
                df['tipx'].diff().fillna(0)**2
                + df['tipy'].diff().fillna(0)**2
            )
            df['tipspeed'] = (
                dist_diff_A * 1e-10 / time_diff_s
            ).replace([np.inf, -np.inf], 0)

        return df

    # =====================================================================
    # SUMMARY DATA
    # =====================================================================

    def _get_summary_data_df(self) -> pd.DataFrame:
        """Return the summary DataFrame, calculating if not cached."""
        if self.summary_df_cache is None:
            self._calculate_summary_statistics()
        return self.summary_df_cache

    def _calculate_summary_statistics(self) -> None:
        """Calculate summary statistics for all runs."""
        logger.info("Calculating summary statistics...")
        all_records = []

        for label in self.full_data_files:
            for file_key in self.full_data_files[label]:
                for run_data in self._extract_all_runs(label, file_key):
                    df = run_data.pop('df')
                    summary_stats = df.mean().to_dict()
                    record = {
                        'dataset_label': label,
                        'file_key': file_key,
                        **run_data,
                        **summary_stats,
                    }
                    all_records.append(record)

        self.summary_df_cache = pd.DataFrame(all_records)

        if (
            not self.summary_df_cache.empty
            and 'id' in self.summary_df_cache.columns
        ):
            self.summary_df_cache['material_type'] = (
                self.summary_df_cache['id'].map(self.material_type_map)
            )
            if 'size' not in self.summary_df_cache.columns:
                self.summary_df_cache['size'] = (
                    self.summary_df_cache['file_key']
                    .str.extract(r'(\d+x\d+y?)')[0]
                )

        logger.debug(
            "Summary DataFrame shape %s", self.summary_df_cache.shape,
        )

    # =====================================================================
    # FILTERING
    # =====================================================================

    def _apply_default_filters(
        self, df: pd.DataFrame, plot_config: dict, x_col: str | None = None,
    ) -> dict:
        """Apply default filters based on data availability."""
        filters = {
            'angle': plot_config.get('angle'),
            'force': plot_config.get('force'),
            'size': plot_config.get('filter_size'),
            'layer': plot_config.get('filter_layer'),
            'speed': plot_config.get('filter_speed'),
            'tip_radius': plot_config.get('filter_tip_radius'),
        }

        if filters['layer'] is None and 'layer' in df.columns:
            unique_layers = df['layer'].dropna().unique()
            if 1 in unique_layers:
                logger.debug("Defaulting to layer 1")
                filters['layer'] = 1

        if x_col == 'force' and filters['angle'] is None:
            logger.debug("Defaulting to angle 0.0 for force plot")
            filters['angle'] = 0.0

        return filters

    def _apply_filters(self, df: pd.DataFrame, filters: dict) -> pd.DataFrame:
        """Apply filters to a DataFrame."""
        for key, value in filters.items():
            if value is not None and key in df.columns:
                original_len = len(df)
                if isinstance(value, list):
                    df = df[df[key].isin(value)]
                else:
                    df = df[df[key] == value]
                logger.debug(
                    "Filter '%s' == '%s': %d -> %d",
                    key, value, original_len, len(df),
                )
        return df

    def _apply_range_filters(
        self, df: pd.DataFrame, plot_config: dict,
    ) -> pd.DataFrame:
        """Apply range-based filters (e.g. filter_force_range)."""
        force_range = plot_config.get('filter_force_range')
        if force_range and len(force_range) == 2 and 'force' in df.columns:
            original_len = len(df)
            df = df[
                (df['force'] >= force_range[0])
                & (df['force'] <= force_range[1])
            ]
            logger.debug(
                "Force range filter [%s, %s]: %d -> %d",
                force_range[0], force_range[1], original_len, len(df),
            )
        return df

    def _apply_material_filter(
        self, df: pd.DataFrame, plot_config: dict, plot_by: str,
    ) -> pd.DataFrame:
        """Apply material/type filters based on plot_by mode."""
        filter_materials = plot_config.get('filter_materials')
        if not filter_materials:
            return df

        filter_values = [v.strip() for v in filter_materials]
        original_len = len(df)

        if plot_by in ('id', 'id_angle'):
            escaped = [re.escape(v) for v in filter_values]
            pattern = '|'.join(
                [f'(?:^|_){v}(?:_|$)' for v in escaped],
            )
            df = df[df['id'].str.contains(pattern, regex=True)]
        elif plot_by == 'material_type':
            ids_to_plot = [
                mid for mid, mtype in self.material_type_map.items()
                if mtype in filter_values
            ]
            df = df[df['id'].isin(ids_to_plot)]

        logger.debug("Material filter: %d -> %d", original_len, len(df))
        return df

    def _remove_outliers(
        self, df: pd.DataFrame, x_col: str, y_col: str,
        threshold: float = 10.0,
    ) -> pd.DataFrame:
        """Remove outliers based on magnitude relative to median."""
        if df.empty:
            return df

        initial_rows = len(df)

        def remove_magnitude_outliers(group):
            if len(group) < 3:
                return group
            median_y = group[y_col].median()
            if abs(median_y) < 1e-6:
                return group
            is_outlier = np.abs(group[y_col]) > threshold * np.abs(median_y)
            return group[~is_outlier]

        cleaned_df = (
            df.groupby(x_col)
            .apply(remove_magnitude_outliers, include_groups=False)
            .reset_index()
        )

        removed = initial_rows - len(cleaned_df)
        if removed > 0:
            logger.debug("Removed %d outlier points", removed)

        return cleaned_df

    # =====================================================================
    # LINEAR FIT
    # =====================================================================

    def _calculate_linear_fit(
        self,
        x_data: np.ndarray,
        y_data: np.ndarray,
        x_range: list | None = None,
    ) -> dict | None:
        """Calculate constrained linear regression through the first point.

        Returns fit parameters or ``None`` if insufficient data.
        """
        if len(x_data) < 2:
            return None

        mask = ~(np.isnan(x_data) | np.isnan(y_data))
        x_clean = np.array(x_data)[mask]
        y_clean = np.array(y_data)[mask]

        if x_range is not None and len(x_range) == 2:
            range_mask = (x_clean >= x_range[0]) & (x_clean <= x_range[1])
            x_clean, y_clean = x_clean[range_mask], y_clean[range_mask]

        if len(x_clean) < 2:
            return None

        x_origin, y_origin = x_clean[0], y_clean[0]
        x_shifted = x_clean - x_origin
        y_shifted = y_clean - y_origin

        slope = np.sum(x_shifted * y_shifted) / np.sum(x_shifted**2)
        intercept = y_origin - slope * x_origin

        y_pred = slope * x_clean + intercept
        residuals = y_clean - y_pred
        rmse = np.sqrt(np.mean(residuals**2))

        ss_res = np.sum(residuals**2)
        ss_tot = np.sum((y_clean - np.mean(y_clean))**2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        n = len(x_clean)
        if n > 1:
            mse = ss_res / (n - 1)
            slope_stderr = np.sqrt(mse / np.sum(x_shifted**2))
        else:
            slope_stderr = 0

        se_intercept = slope_stderr * np.abs(x_origin)

        return {
            'slope': slope,
            'intercept': intercept,
            'slope_stderr': slope_stderr,
            'intercept_stderr': se_intercept,
            'r_squared': r_squared,
            'rmse': rmse,
        }

    # =====================================================================
    # PLOTTING HELPERS
    # =====================================================================

    def _plot_series(
        self, ax, x_data, y_data, label, plot_style, add_fit,
        fit_x_range, std_data=None, *, show_error_bands=True,
        color_idx=0,
    ):
        """Plot a single data series with optional fit and error bands.

        Returns the line colour used.
        """
        s = self.settings
        marker = s["markers"]["style"]

        palette = s["colors"].get("palette", "gem12")
        if palette == "gem12":
            color = GEM12_COLORS[color_idx % len(GEM12_COLORS)]
        else:
            color = None

        if plot_style == 'scatter':
            scatter = ax.scatter(
                x_data, y_data, label=label,
                s=s["markers"]["size"]**2, color=color,
            )
            if color is None:
                color = scatter.get_facecolors()[0]
        else:
            linestyle = '' if add_fit else '-'
            line = ax.plot(
                x_data, y_data, marker=marker, linestyle=linestyle,
                linewidth=s["lines"]["width"], label=label, color=color,
                markersize=s["markers"]["size"],
            )
            if color is None:
                color = line[0].get_color()

        if std_data is not None and show_error_bands:
            lower_bound = np.maximum(y_data - std_data, 0)
            upper_bound = y_data + std_data
            ax.fill_between(
                x_data, lower_bound, upper_bound,
                alpha=s["error_bands"]["alpha"], color=color,
            )

        if add_fit:
            fit_params = self._calculate_linear_fit(
                np.array(x_data), np.array(y_data), fit_x_range,
            )
            if fit_params:
                x_min = fit_x_range[0] if fit_x_range else x_data.min()
                x_max = fit_x_range[1] if fit_x_range else x_data.max()
                x_fit = np.linspace(x_min, x_max, 100)
                y_fit = fit_params['slope'] * x_fit + fit_params['intercept']
                ax.plot(
                    x_fit, y_fit, s["lines"]["fit_style"],
                    alpha=s["lines"]["fit_alpha"],
                    linewidth=s["lines"]["width"], color=color,
                )

        return color

    def _finalize_plot(
        self, ax, plot_config: dict,
        x_col: str | None = None, y_col: str | None = None,
        *, x_label: str | None = None, y_label: str | None = None,
    ) -> None:
        """Apply final formatting to a plot (MATLAB-style)."""
        s = self.settings

        ax.set_xlabel(
            x_label or plot_config.get('x_label', x_col or ''),
            fontsize=s["fonts"]["axis_label"],
        )
        ax.set_ylabel(
            y_label or plot_config.get('y_label', y_col or ''),
            fontsize=s["fonts"]["axis_label"],
        )
        ax.tick_params(
            axis='both', which='major',
            labelsize=s["fonts"]["tick_label"],
        )

        axes_config = s.get("axes", {})
        use_sci = plot_config.get(
            'use_scientific_notation',
            axes_config.get('use_scientific_notation', False),
        )
        if use_sci:
            scilimits = axes_config.get('scilimits', [-2, 2])
            ax.ticklabel_format(
                style='sci', axis='both',
                scilimits=tuple(scilimits), useMathText=True,
            )
            ax.xaxis.get_offset_text().set_fontsize(s["fonts"]["tick_label"])
            ax.yaxis.get_offset_text().set_fontsize(s["fonts"]["tick_label"])

        title = plot_config.get('title')
        if title:
            ax.set_title(title, fontsize=s["fonts"]["title"])

        grid_config = s.get("grid", {})
        if grid_config.get("show", True):
            which = grid_config.get("which", "both")
            if which in ("major", "both"):
                ax.grid(
                    True, which='major',
                    linestyle=grid_config.get("major_style", "-"),
                    alpha=grid_config.get("major_alpha", 0.5),
                )
            if which in ("minor", "both"):
                ax.minorticks_on()
                ax.grid(
                    True, which='minor',
                    linestyle=grid_config.get("minor_style", ":"),
                    alpha=grid_config.get("minor_alpha", 0.3),
                )

        if ax.get_legend_handles_labels()[1]:
            legend_loc = plot_config.get(
                'legend_location', s["legend"]["location"],
            )
            ax.legend(loc=legend_loc, fontsize=s["fonts"]["legend"])

    def _apply_axis_limits(self, ax, plot_config: dict) -> None:
        """Apply explicit x and y axis limits from plot config."""
        y_limits = plot_config.get('y_limits')
        if y_limits:
            if y_limits[0] is not None:
                ax.set_ylim(bottom=y_limits[0])
            if len(y_limits) > 1 and y_limits[1] is not None:
                ax.set_ylim(top=y_limits[1])

        x_limits = plot_config.get('x_limits')
        if x_limits:
            if x_limits[0] is not None:
                ax.set_xlim(left=x_limits[0])
            if len(x_limits) > 1 and x_limits[1] is not None:
                ax.set_xlim(right=x_limits[1])

    def _save_plot(self, fig, filename: str | None) -> None:
        """Save the plot to file(s) in configured formats."""
        if not filename:
            logger.warning("No filename specified. Plot not saved.")
            plt.close(fig)
            return

        export_config = self.settings.get("export", {})
        formats = export_config.get("formats", ["png"])
        transparent = export_config.get("transparent", False)

        base_name = Path(filename).stem
        original_ext = Path(filename).suffix.lstrip('.')

        if original_ext and original_ext not in formats:
            formats = [original_ext] + list(formats)

        try:
            fig.subplots_adjust(
                left=0.13, bottom=0.13, right=0.97, top=0.97,
            )
        except Exception as e:
            logger.warning("subplots_adjust failed: %s", e)

        for fmt in formats:
            output_path = self.output_dir / f"{base_name}.{fmt}"
            fig.savefig(
                output_path, dpi=self.settings["figure"]["dpi"],
                format=fmt, transparent=transparent,
                bbox_inches='tight', pad_inches=0.1,
            )
            logger.info("Generated plot: %s", output_path)

        plt.close(fig)

    # =====================================================================
    # SUMMARY PLOT
    # =====================================================================

    def _generate_summary_plot(self, plot_config: dict) -> None:
        """Generate a summary plot (main plot type)."""
        summary_df = self._get_summary_data_df()
        if summary_df.empty:
            logger.warning("Summary data is empty. Skipping plot.")
            return

        title = plot_config.get('title', '(no title)')
        logger.debug("Generating plot: %s", title)

        df = summary_df.copy()
        datasets = plot_config.get('datasets')
        if datasets:
            df = df[df['dataset_label'].isin(datasets)]
            logger.debug("Dataset filter: %d -> %d", len(summary_df), len(df))

        plot_by = plot_config.get('plot_by', 'id')
        plot_style = plot_config.get('plot_style', 'line')
        x_col = plot_config['x_axis']
        y_col = plot_config['y_axis']
        add_fit = plot_config.get('add_linear_fit', False)
        fit_x_range = plot_config.get('fit_x_range')
        show_dataset = plot_config.get('show_dataset_in_legend', False)
        show_error_bands = plot_config.get('show_error_bands', True)

        filters = self._apply_default_filters(df, plot_config, x_col)
        df = self._apply_filters(df, filters)
        df = self._apply_range_filters(df, plot_config)
        df = self._apply_material_filter(df, plot_config, plot_by)

        if df.empty:
            logger.warning("No data left after filtering. Skipping plot.")
            return

        if y_col not in df.columns:
            logger.error(
                "y-axis column '%s' not found in data. Skipping.", y_col,
            )
            return

        df = self._remove_outliers(df, x_col, y_col)
        if df.empty:
            logger.warning("No data left after outlier removal. Skipping.")
            return

        fig, ax = plt.subplots(figsize=self.figure_size)

        if plot_by == 'dataset_label':
            group_col = 'dataset_label'
            aggregate = True
        elif plot_by == 'material_type':
            group_col = 'material_type'
            aggregate = True
        elif plot_by == 'id_angle':
            group_col = ['id', 'angle']
            aggregate = False
        else:
            group_col = 'id'
            aggregate = False

        color_idx = 0
        for group_name, group in df.groupby(group_col):
            if plot_by == 'material_type':
                label = self.type_display_names.get(group_name, group_name)
            elif plot_by == 'id_angle':
                label = f"{group_name[0]}_{int(group_name[1])}"
            elif show_dataset and 'dataset_label' in group.columns:
                dataset = group['dataset_label'].iloc[0]
                label = f"{group_name} ({dataset})"
            else:
                label = group_name

            if aggregate:
                plot_data = (
                    group.groupby(x_col)[y_col]
                    .agg(['mean', 'std']).reset_index()
                )
                plot_data = plot_data.sort_values(by=x_col)
                self._plot_series(
                    ax, plot_data[x_col], plot_data['mean'], label,
                    plot_style, add_fit, fit_x_range, plot_data['std'],
                    show_error_bands=show_error_bands, color_idx=color_idx,
                )
            else:
                group = group.sort_values(by=x_col)
                self._plot_series(
                    ax, group[x_col], group[y_col], label,
                    plot_style, add_fit, fit_x_range,
                    show_error_bands=show_error_bands, color_idx=color_idx,
                )

            logger.debug("Plotted %s (%d points)", group_name, len(group))
            color_idx += 1

        # Auto y-limits
        if y_col == 'cof' and x_col == 'force':
            zoom_df = df[df[x_col] > 10]
            if zoom_df.empty:
                zoom_df = df
        else:
            zoom_df = df

        if not zoom_df.empty:
            min_y, max_y = zoom_df[y_col].min(), zoom_df[y_col].max()
            padding = max((max_y - min_y) * 0.1, 0.1)
            ax.set_ylim(min_y - padding, max_y + padding)

        self._apply_axis_limits(ax, plot_config)
        self._finalize_plot(ax, plot_config, x_col, y_col)
        self._save_plot(fig, plot_config.get('filename'))

    # =====================================================================
    # SCATTER COMPARISON PLOT
    # =====================================================================

    def _load_external_json(
        self, source_config: dict,
    ) -> tuple[list | None, np.ndarray | None, np.ndarray | None]:
        """Load data from an external JSON file with materials mapping."""
        file_path = source_config.get('file')
        if not file_path:
            return None, None, None

        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            materials = data.get(
                source_config.get('material_column', 'materials'), [],
            )
            values = np.array(
                data.get(source_config.get('value_column', 'tribIndex'), []),
            )
            errors = np.array(
                data.get(source_config.get('error_column', 'dev'), []),
            )

            return materials, values, errors
        except Exception as e:
            logger.error("Loading external JSON file %s: %s", file_path, e)
            return None, None, None

    def _get_aggregated_source_data(
        self,
        summary_df: pd.DataFrame,
        source_config: dict,
        material_list: list | None = None,
    ) -> tuple[list | None, np.ndarray | None, np.ndarray | None]:
        """Extract data with optional force-range averaging.

        Returns ``(materials, values, errors)`` arrays.
        """
        dataset = source_config.get('dataset')
        metric = source_config.get('metric')

        if not dataset or not metric:
            logger.error("Source must specify 'dataset' and 'metric'")
            return None, None, None

        df = summary_df[summary_df['dataset_label'] == dataset].copy()

        for key in ('filter_layer', 'filter_size'):
            value = source_config.get(key)
            col = key.replace('filter_', '')
            if value is not None and col in df.columns:
                df = df[df[col] == value]

        angle = source_config.get('angle')
        if angle is not None and 'angle' in df.columns:
            if isinstance(angle, list):
                df = df[df['angle'].isin(angle)]
            else:
                df = df[df['angle'] == angle]

        if material_list is not None and 'id' in df.columns:
            matched_ids = []
            for mat in material_list:
                for df_id in df['id'].unique():
                    if (
                        mat in df_id
                        or df_id in mat
                        or mat.replace('_', '') in df_id.replace('_', '')
                    ):
                        matched_ids.append(df_id)
            df = df[df['id'].isin(matched_ids)]

        if df.empty:
            logger.warning("No data found for source: %s", source_config)
            return None, None, None

        force_range = source_config.get('force_range')
        error_metric = source_config.get('error_metric', 'slope_stderr')

        materials_out: list = []
        values_out: list = []
        errors_out: list = []

        for mat_id in df['id'].unique():
            mat_df = df[df['id'] == mat_id].copy()

            if force_range and len(force_range) == 2:
                mat_df = mat_df[
                    (mat_df['force'] >= force_range[0])
                    & (mat_df['force'] <= force_range[1])
                ]

                if len(mat_df) < 2:
                    continue

                avg_value = mat_df[metric].mean()
                fit = self._calculate_linear_fit(
                    mat_df['force'].values, mat_df[metric].values,
                )

                if fit:
                    error_map = {
                        'slope_stderr': fit['slope_stderr'],
                        'rmse': fit['rmse'],
                        'r_squared': 1 - fit['r_squared'],
                    }
                    error = error_map.get(error_metric, fit['slope_stderr'])
                else:
                    error = mat_df[metric].std()

                materials_out.append(mat_id)
                values_out.append(avg_value)
                errors_out.append(error)
            else:
                force = source_config.get('force')
                if force is not None:
                    mat_df = mat_df[mat_df['force'] == force]

                if mat_df.empty:
                    continue

                materials_out.append(mat_id)
                values_out.append(mat_df[metric].mean())
                errors_out.append(
                    mat_df[metric].std() if len(mat_df) > 1 else 0,
                )

        return materials_out, np.array(values_out), np.array(errors_out)

    @staticmethod
    def _iterative_outlier_removal(
        x: np.ndarray, y: np.ndarray,
        x_err: np.ndarray | None, y_err: np.ndarray | None,
        materials: list, num_remove: int,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list]:
        """Iteratively remove points with largest residuals from OLS fit."""
        from scipy import stats  # noqa: PLC0415

        x = np.array(x)
        y = np.array(y)
        x_err = np.array(x_err) if x_err is not None else np.zeros_like(x)
        y_err = np.array(y_err) if y_err is not None else np.zeros_like(y)
        materials = list(materials)
        removed = []

        for _ in range(min(num_remove, len(x) - 2)):
            if len(x) <= 2:
                break

            slope, intercept, _, _, _ = stats.linregress(x, y)
            y_pred = slope * x + intercept
            residuals = np.abs(y - y_pred)

            max_idx = np.argmax(residuals)
            removed.append(materials[max_idx])

            mask = np.ones(len(x), dtype=bool)
            mask[max_idx] = False
            x = x[mask]
            y = y[mask]
            x_err = x_err[mask]
            y_err = y_err[mask]
            materials = [m for i, m in enumerate(materials) if mask[i]]

        if removed:
            logger.info(
                "Outlier removal: removed %d points: %s",
                len(removed), removed,
            )

        return x, y, x_err, y_err, materials

    def _generate_scatter_comparison(self, plot_config: dict) -> None:
        """Generate a scatter plot comparing two data sources."""
        x_source = plot_config.get('x_source', {})
        y_source = plot_config.get('y_source', {})

        if not x_source or not y_source:
            logger.error(
                "scatter_comparison requires 'x_source' and 'y_source'",
            )
            return

        summary_df = self._get_summary_data_df()

        # Load data from both sources
        if 'file' in x_source:
            x_materials, x_data, x_errors = self._load_external_json(
                x_source,
            )
            if x_materials is None:
                return

            y_materials, y_data, y_errors = self._get_aggregated_source_data(
                summary_df, y_source, x_materials,
            )
            if y_materials is None:
                return

            # Match materials between x and y
            matched_x, matched_y = [], []
            matched_x_err, matched_y_err = [], []
            matched_materials = []

            for i, x_mat in enumerate(x_materials):
                for j, y_mat in enumerate(y_materials):
                    if (
                        x_mat in y_mat
                        or y_mat in x_mat
                        or x_mat.replace('_', '') in y_mat.replace('_', '')
                    ):
                        matched_x.append(x_data[i])
                        matched_y.append(y_data[j])
                        matched_x_err.append(
                            x_errors[i] if len(x_errors) > i else 0,
                        )
                        matched_y_err.append(
                            y_errors[j] if len(y_errors) > j else 0,
                        )
                        matched_materials.append(x_mat)
                        break

            x_data = np.array(matched_x)
            y_data = np.array(matched_y)
            x_errors = np.array(matched_x_err)
            y_errors = np.array(matched_y_err)
            materials = matched_materials
        else:
            x_materials, x_data, x_errors = self._get_aggregated_source_data(
                summary_df, x_source,
            )
            y_materials, y_data, y_errors = self._get_aggregated_source_data(
                summary_df, y_source, x_materials,
            )

            if x_data is None or y_data is None:
                logger.error(
                    "Could not extract data for scatter comparison",
                )
                return

            materials = x_materials if x_materials else []
            if x_errors is None:
                x_errors = np.zeros_like(x_data)
            if y_errors is None:
                y_errors = np.zeros_like(y_data)

        if len(x_data) == 0 or len(y_data) == 0:
            logger.error("No matched data points for scatter comparison")
            return

        if len(x_data) != len(y_data):
            logger.warning(
                "Data size mismatch: x=%d, y=%d. Using minimum.",
                len(x_data), len(y_data),
            )
            min_len = min(len(x_data), len(y_data))
            x_data = x_data[:min_len]
            y_data = y_data[:min_len]
            x_errors = x_errors[:min_len]
            y_errors = y_errors[:min_len]
            materials = materials[:min_len]

        num_outliers = plot_config.get('iterative_outlier_removal', 0)
        if num_outliers > 0:
            x_data, y_data, x_errors, y_errors, materials = (
                self._iterative_outlier_removal(
                    x_data, y_data, x_errors, y_errors,
                    materials, num_outliers,
                )
            )

        # Create figure
        fig, ax = plt.subplots(figsize=self.figure_size)

        palette = self.settings["colors"].get("palette", "gem12")
        show_error_bars = plot_config.get('show_error_bars', False)
        color_by_class = plot_config.get('color_by_material_class', False)

        if color_by_class and materials:
            self._plot_scatter_by_class(
                ax, x_data, y_data, x_errors, y_errors,
                materials, palette, show_error_bars,
            )
        else:
            point_color = GEM12_COLORS[0] if palette == "gem12" else None
            if (
                show_error_bars
                and (np.any(x_errors > 0) or np.any(y_errors > 0))
            ):
                ax.errorbar(
                    x_data, y_data,
                    xerr=x_errors if np.any(x_errors > 0) else None,
                    yerr=y_errors if np.any(y_errors > 0) else None,
                    fmt='o', color=point_color,
                    markersize=self.settings["markers"]["size"],
                    capsize=3, capthick=1, elinewidth=1,
                )
            else:
                ax.scatter(
                    x_data, y_data,
                    s=self.settings["markers"]["size"]**2,
                    color=point_color,
                )

        # Point labels
        if plot_config.get('show_point_labels', False) and materials:
            x_range = x_data.max() - x_data.min()
            dx = x_range * 0.01
            label_fontsize = plot_config.get('point_label_fontsize', 8)
            for i, mat in enumerate(materials):
                ax.text(
                    x_data[i] + dx, y_data[i], mat,
                    fontsize=label_fontsize,
                )

        # y=x reference line
        if plot_config.get('show_identity_line', False):
            lims = [
                min(x_data.min(), y_data.min()),
                max(x_data.max(), y_data.max()),
            ]
            ax.plot(lims, lims, '--', color='gray', alpha=0.5, label='y=x')

        # Linear fit
        fit = None
        if plot_config.get('add_linear_fit', False):
            fit = self._calculate_linear_fit(x_data, y_data)
            if fit:
                x_fit = np.linspace(
                    x_data.min() * 0.9, x_data.max() * 1.1, 100,
                )
                y_fit = fit['slope'] * x_fit + fit['intercept']
                fit_color = GEM12_COLORS[1] if palette == "gem12" else 'red'
                ax.plot(
                    x_fit, y_fit, '--', color=fit_color, alpha=0.8,
                    linewidth=self.settings["lines"]["width"],
                    label=f"Fit (R²={fit['r_squared']:.4f})",
                )

        # R² display
        if plot_config.get('show_r_squared', False):
            if fit is None:
                fit = self._calculate_linear_fit(x_data, y_data)
            if fit:
                r2_text = f"R² = {fit['r_squared']:.4f}"
                if num_outliers > 0:
                    r2_text += f" (Filtered {num_outliers})"
                ax.text(
                    0.05, 0.95, r2_text, transform=ax.transAxes,
                    fontsize=self.settings["fonts"]["legend"],
                    fontweight='bold', verticalalignment='top',
                )

        # Axis formatting via shared helpers
        x_label = plot_config.get(
            'x_label',
            f"{x_source.get('dataset', 'X')} {x_source.get('metric', '')}",
        )
        y_label = plot_config.get(
            'y_label',
            f"{y_source.get('dataset', 'Y')} {y_source.get('metric', '')}",
        )
        self._finalize_plot(
            ax, plot_config, x_label=x_label, y_label=y_label,
        )
        self._apply_axis_limits(ax, plot_config)
        self._save_plot(fig, plot_config.get('filename'))

    def _plot_scatter_by_class(
        self, ax, x_data, y_data, x_errors, y_errors,
        materials, palette, show_error_bars,
    ) -> None:
        """Plot scatter points coloured by material class."""
        prefixes = {
            'h_': 'hexagonal', 't_': 'trigonal',
            'p_': 'puckered', 'b_': 'buckled',
        }

        def get_class(mat_name):
            for prefix, class_name in prefixes.items():
                if mat_name.startswith(prefix):
                    return class_name
            return 'bi-buckled'

        class_indices: dict[str, list[int]] = {}
        for i, mat in enumerate(materials):
            class_indices.setdefault(get_class(mat), []).append(i)

        for class_idx, (class_name, indices) in enumerate(
            sorted(class_indices.items()),
        ):
            color = (
                GEM12_COLORS[class_idx % len(GEM12_COLORS)]
                if palette == "gem12" else None
            )

            c_x = x_data[indices]
            c_y = y_data[indices]
            c_x_err = x_errors[indices] if x_errors is not None else None
            c_y_err = y_errors[indices] if y_errors is not None else None

            has_err = (
                (c_x_err is not None and np.any(c_x_err > 0))
                or (c_y_err is not None and np.any(c_y_err > 0))
            )

            if show_error_bars and has_err:
                ax.errorbar(
                    c_x, c_y,
                    xerr=(
                        c_x_err
                        if c_x_err is not None and np.any(c_x_err > 0)
                        else None
                    ),
                    yerr=(
                        c_y_err
                        if c_y_err is not None and np.any(c_y_err > 0)
                        else None
                    ),
                    fmt='o', color=color, label=class_name,
                    markersize=self.settings["markers"]["size"],
                    capsize=3, capthick=1, elinewidth=1,
                )
            else:
                ax.scatter(
                    c_x, c_y,
                    s=self.settings["markers"]["size"]**2,
                    color=color, label=class_name,
                )

    # =====================================================================
    # TIMESERIES PLOT
    # =====================================================================

    def _generate_timeseries_plot(self, plot_config: dict) -> None:
        """Generate a timeseries plot."""
        datasets = plot_config.get(
            'datasets', [self.labels[0]] if self.labels else [],
        )
        if not datasets:
            logger.error("No dataset specified for timeseries plot.")
            return

        label = datasets[0]
        file_key = plot_config.get('filter_size')
        if not file_key:
            logger.error("'filter_size' is required for timeseries plots.")
            return

        _, local_metadata = self._load_full_data(label, file_key)
        if not local_metadata:
            logger.error(
                "Could not load metadata for file_key '%s'.", file_key,
            )
            return

        time_series = local_metadata.get('time_series')
        if not time_series:
            logger.error("'time_series' not found in metadata.")
            return

        all_runs = list(self._extract_all_runs(label, file_key))
        if not all_runs:
            logger.warning(
                "No runs found for label '%s' and file_key '%s'.",
                label, file_key,
            )
            return

        # Build filters
        force_filter = None
        if not plot_config.get('plot_all_forces'):
            force_filter = (
                plot_config.get('filter_forces')
                or plot_config.get('force')
            )

        filters = {
            'id': plot_config.get('filter_materials'),
            'force': force_filter,
            'angle': plot_config.get('angle'),
            'layer': plot_config.get('filter_layer'),
            'speed': plot_config.get('filter_speed'),
            'tip_radius': plot_config.get('filter_tip_radius'),
        }

        if filters['layer'] is None:
            layers = {
                run.get('layer')
                for run in all_runs if 'layer' in run
            }
            if 1 in layers:
                filters['layer'] = 1

        if filters['angle'] is None:
            filters['angle'] = 0.0

        # Filter runs
        filtered_runs = []
        for run in all_runs:
            match = True
            for key, value in filters.items():
                if value is None:
                    continue
                run_value = run.get(key)
                if run_value is None:
                    match = False
                    break
                if key == 'id' and isinstance(value, list):
                    if not any(v in run_value for v in value):
                        match = False
                        break
                elif isinstance(value, list):
                    if run_value not in value:
                        match = False
                        break
                elif run_value != value:
                    match = False
                    break
            if match:
                filtered_runs.append(run)

        if not filtered_runs:
            logger.warning("No runs matched filters for timeseries plot.")
            return

        if force_filter and isinstance(force_filter, list):
            force_order = {
                force: idx for idx, force in enumerate(force_filter)
            }
            filtered_runs.sort(
                key=lambda r: force_order.get(
                    r.get('force'), len(force_filter),
                ),
            )

        y_col = plot_config.get('y_axis')
        if not y_col:
            logger.error("Missing y-axis for timeseries plot.")
            return

        fig, ax = plt.subplots(figsize=self.figure_size)

        palette = self.settings["colors"].get("palette", "gem12")
        time_scale = plot_config.get('time_scale', 1.0)
        scaled_time_series = [t * time_scale for t in time_series]

        secondary_y_col = plot_config.get('secondary_y_axis')
        secondary_y_label = plot_config.get('secondary_y_label')
        secondary_y_scale = plot_config.get('secondary_y_scale', 1.0)
        ax2 = ax.twinx() if secondary_y_col else None

        for idx, run in enumerate(filtered_runs):
            df = run['df']
            if y_col not in df.columns:
                logger.warning(
                    "y-axis '%s' not found for run %s. Skipping.",
                    y_col, run.get('id'),
                )
                continue

            label_parts = [run.get('id', 'N/A')]
            if 'force' in run:
                label_parts.append(f"F={run['force']}nN")

            color = (
                GEM12_COLORS[idx % len(GEM12_COLORS)]
                if palette == "gem12" else None
            )
            ax.plot(
                scaled_time_series, df[y_col],
                label=", ".join(label_parts), color=color,
                linewidth=self.settings["lines"]["width"],
            )

            if secondary_y_col:
                if secondary_y_col not in df.columns:
                    logger.warning(
                        "Secondary y-axis '%s' not found for run %s.",
                        secondary_y_col, run.get('id'),
                    )
                else:
                    sec_label = (
                        ", ".join(label_parts) + f" {secondary_y_col}"
                    )
                    sec_color = (
                        GEM12_COLORS[(idx + 1) % len(GEM12_COLORS)]
                        if palette == "gem12" else None
                    )
                    ax2.plot(
                        scaled_time_series,
                        df[secondary_y_col] * secondary_y_scale,
                        label=sec_label, color=sec_color,
                        linewidth=self.settings["lines"]["width"],
                        linestyle='--',
                    )

        self._finalize_plot(ax, plot_config, 'time', y_col)

        if ax2 and secondary_y_label:
            ax2.set_ylabel(
                secondary_y_label,
                fontsize=self.settings["fonts"]["axis_label"],
            )
            ax2.tick_params(
                axis='both', which='major',
                labelsize=self.settings["fonts"]["tick_label"],
            )

        if ax2:
            handles1, labels1 = ax.get_legend_handles_labels()
            handles2, labels2 = ax2.get_legend_handles_labels()
            if labels2:
                ax.legend(
                    handles1 + handles2, labels1 + labels2,
                    loc=self.settings["legend"]["location"],
                    fontsize=self.settings["fonts"]["legend"],
                )

        self._save_plot(fig, plot_config.get('filename'))

    # =====================================================================
    # CORRELATION PLOTS
    # =====================================================================

    def _generate_correlation_plots(self, plot_config: dict) -> None:
        """Generate correlation heatmaps from friction ranking files."""
        logger.info("Generating correlation plots...")

        ranking_files = list(
            self.output_dir.glob('friction_ranking_*.json'),
        )
        if not ranking_files:
            logger.error("No friction_ranking_*.json files found.")
            return

        all_ranks = []
        for f_path in ranking_files:
            size_match = re.search(
                r'friction_ranking_(.+)\.json', f_path.name,
            )
            if not size_match:
                continue
            size = size_match.group(1)

            with open(f_path, 'r') as f:
                data = json.load(f)
                for force_key, material_list in data.items():
                    force = float(force_key[1:])
                    for rank, material_data in enumerate(material_list, 1):
                        all_ranks.append({
                            'size': size, 'force': force,
                            'material': material_data['material'],
                            'rank': rank,
                        })

        if not all_ranks:
            logger.error("Could not parse ranking data.")
            return

        rank_df = pd.DataFrame(all_ranks)
        correlate_by = plot_config.get('correlate_by')

        if correlate_by == 'size':
            self._plot_correlation_heatmap(rank_df, 'size', plot_config)
        elif correlate_by == 'force':
            self._plot_correlation_heatmap(rank_df, 'force', plot_config)
        elif correlate_by == 'pairwise':
            self._plot_pairwise_correlation(rank_df, plot_config)
        else:
            logger.error("Unknown correlation type '%s'", correlate_by)

    def _plot_correlation_heatmap(
        self, rank_df: pd.DataFrame, correlate_by: str, plot_config: dict,
    ) -> None:
        """Generic correlation heatmap plotter."""
        import seaborn as sns  # noqa: PLC0415

        if correlate_by == 'size':
            force = plot_config.get('correlation_force', 30)
            df = rank_df[rank_df['force'] == force]
            pivot_df = df.pivot_table(
                index='material', columns='size',
                values='rank', aggfunc='mean',
            )
            title = f'Rank Correlation Across Sizes (Force={force}nN)'
            filename = plot_config.get(
                'filename', f'rank_corr_by_size_f{force}.png',
            )
        else:
            for size, group in rank_df.groupby('size'):
                pivot_df = group.pivot_table(
                    index='material', columns='force',
                    values='rank', aggfunc='mean',
                )
                pivot_df.dropna(inplace=True)

                if len(pivot_df) < 2 or len(pivot_df.columns) < 2:
                    continue

                corr = pivot_df.corr(method='spearman')

                fig, ax = plt.subplots(figsize=(10, 8))
                sns.heatmap(corr, annot=True, cmap='crest', fmt='.2f', ax=ax)
                ax.set_title(
                    f'Rank Correlation Across Forces (Size={size})',
                )

                filename = (
                    plot_config.get('filename_prefix', 'rank_corr_by_force')
                    + f'_{size}.png'
                )
                self._save_plot(fig, filename)
            return

        pivot_df.dropna(inplace=True)
        if len(pivot_df) < 2:
            logger.error("Not enough data for correlation matrix.")
            return

        corr = pivot_df.corr(method='spearman')

        fig, ax = plt.subplots(figsize=(8, 6))
        sns.heatmap(corr, annot=True, cmap='crest', fmt='.2f', ax=ax)
        ax.set_title(title)

        self._save_plot(fig, filename)

    def _plot_pairwise_correlation(
        self, rank_df: pd.DataFrame, plot_config: dict,
    ) -> None:
        """Plot force-vs-force correlation between two sizes."""
        import seaborn as sns  # noqa: PLC0415

        sizes = plot_config.get('sizes_to_compare')
        if not sizes or len(sizes) != 2:
            logger.error(
                "'pairwise' requires 'sizes_to_compare' with two sizes.",
            )
            return

        size1, size2 = sizes
        df1 = rank_df[rank_df['size'] == size1]
        df2 = rank_df[rank_df['size'] == size2]

        forces1 = sorted(df1['force'].unique())
        forces2 = sorted(df2['force'].unique())

        if not forces1 or not forces2:
            logger.error("No force data for sizes: %s, %s", size1, size2)
            return

        corr_matrix = pd.DataFrame(
            index=forces2, columns=forces1, dtype=float,
        )

        for f1 in forces1:
            for f2 in forces2:
                ranks1 = (
                    df1[df1['force'] == f1]
                    .groupby('material')['rank'].mean()
                )
                ranks2 = (
                    df2[df2['force'] == f2]
                    .groupby('material')['rank'].mean()
                )
                combined = pd.DataFrame(
                    {'r1': ranks1, 'r2': ranks2},
                ).dropna()

                if len(combined) > 1:
                    corr_matrix.loc[f2, f1] = combined['r1'].corr(
                        combined['r2'], method='spearman',
                    )

        fig, ax = plt.subplots(figsize=(12, 10))
        sns.heatmap(
            corr_matrix, annot=True, fmt='.2f', cmap='crest',
            cbar_kws={'label': "Spearman's Correlation"},
            linewidths=.5, ax=ax,
        )

        ax.set_title(f'Force vs Force Correlation ({size1} vs {size2})')
        ax.set_xlabel(f'Force (nN) for {size1}')
        ax.set_ylabel(f'Force (nN) for {size2}')

        filename = plot_config.get(
            'filename',
            f'force_vs_force_corr_{size1}_vs_{size2}.png',
        )
        self._save_plot(fig, filename)

    # =====================================================================
    # FRICTION RANKING
    # =====================================================================

    def rank_friction(self, plot_config: dict) -> None:
        """Rank materials by friction and export to JSON."""
        logger.info("Generating friction rankings...")

        summary_df = self._get_summary_data_df()
        if summary_df.empty:
            logger.warning("Summary data is empty.")
            return

        metrics = plot_config.get('rank_by', ['lf'])
        if not isinstance(metrics, list):
            metrics = [metrics]

        df = summary_df.copy()
        layer = plot_config.get('filter_layer')
        if layer:
            df = df[df['layer'] == layer]

        angle = plot_config.get('angle', 0)
        df = df[df['angle'] == angle]

        force = plot_config.get('force')
        if force is not None:
            df = df[df['force'] == force]

        if df.empty:
            logger.warning("No data available for ranking.")
            return

        fit_x_range = plot_config.get('fit_x_range')

        for metric in metrics:
            if metric not in df.columns:
                logger.warning("Metric '%s' not found. Skipping.", metric)
                continue

            rank_df = df[df[metric] > 0].copy()
            if rank_df.empty:
                continue

            agg_df = (
                rank_df.groupby(['size', 'force', 'id'])[metric]
                .mean().reset_index()
            )

            for size, group in agg_df.groupby('size'):
                fits = {}
                for mat_id, mat_group in group.groupby('id'):
                    fit = self._calculate_linear_fit(
                        mat_group['force'].values,
                        mat_group[metric].values,
                        fit_x_range,
                    )
                    fits[mat_id] = fit

                ranks_by_force = {}
                for f, f_group in group.groupby('force'):
                    ranked = f_group.sort_values(
                        metric, ascending=False,
                    ).reset_index()
                    ranked['rank'] = ranked.index + 1

                    materials = []
                    for _, row in ranked.iterrows():
                        record = {
                            'material': row['id'],
                            'rank': row['rank'],
                            'metric': metric,
                            'mean_value': row[metric],
                        }
                        if fits.get(row['id']):
                            record.update({
                                'fit_slope_stderr': fits[row['id']]['slope_stderr'],
                                'fit_r_squared': fits[row['id']]['r_squared'],
                                'fit_rmse': fits[row['id']]['rmse'],
                            })
                        materials.append(record)

                    ranks_by_force[f"f{f}"] = materials

                if plot_config.get('filename'):
                    filename = plot_config['filename']
                else:
                    layer_str = f"_layer{layer}" if layer else ""
                    filename = (
                        f'friction_ranking_{metric}_{size}{layer_str}.json'
                    )

                output_path = self.output_dir / filename
                with open(output_path, 'w') as f:
                    json.dump(ranks_by_force, f, indent=4)
                logger.info("Exported ranking to %s", output_path)

    # =====================================================================
    # MAIN DISPATCHER
    # =====================================================================

    def generate_plot(self, plot_config: dict) -> None:
        """Dispatch to the appropriate plot generation method."""
        plot_type = plot_config.get('plot_type', 'summary')

        dispatch = {
            'summary': self._generate_summary_plot,
            'timeseries': self._generate_timeseries_plot,
            'scatter_comparison': self._generate_scatter_comparison,
            'rank_friction': self.rank_friction,
            'correlation': self._generate_correlation_plots,
        }

        if plot_type in dispatch:
            dispatch[plot_type](plot_config)
        else:
            logger.error("Unknown plot type '%s'", plot_type)
