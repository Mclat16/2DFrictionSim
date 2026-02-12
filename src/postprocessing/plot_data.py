"""
Plot Data - Refactored
Generates plots from simulation data with configurable aesthetics.

Usage:
    python plot_data.py plots.json --output_dir plots
    python plot_data.py plots.json --output_dir plots --settings plot_settings.json
    python plot_data.py plots.json --output_dir plots --verbose
    python plot_data.py plots.json --output_dir plots --quiet
"""

import json
import argparse
import os
import re
import glob
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import pandas as pd
from scipy import stats


# =============================================================================
# LOGGING UTILITIES
# =============================================================================

class Logger:
    """Simple logger with verbosity levels."""
    QUIET = 0
    NORMAL = 1
    VERBOSE = 2
    
    def __init__(self, level=NORMAL):
        self.level = level
    
    def error(self, msg):
        """Always print errors."""
        print(f"Error: {msg}")
    
    def warning(self, msg):
        """Print warnings at NORMAL level and above."""
        if self.level >= self.NORMAL:
            print(f"Warning: {msg}")
    
    def info(self, msg):
        """Print info at NORMAL level and above."""
        if self.level >= self.NORMAL:
            print(msg)
    
    def debug(self, msg):
        """Print debug info only at VERBOSE level."""
        if self.level >= self.VERBOSE:
            print(f"  [DEBUG] {msg}")

# Global logger instance
log = Logger()

# =============================================================================
# DATABASE INTEGRATION HELPERS
# =============================================================================

def _partition_results(results, n_partitions):
    """Partition query results into n groups for multiple datasets."""
    simulations = results.simulations
    partition_size = len(simulations) // n_partitions
    
    partitions = []
    for i in range(n_partitions):
        start = i * partition_size
        end = start + partition_size if i < n_partitions - 1 else len(simulations)
        partitions.append(simulations[start:end])
    
    return partitions


def _write_results_to_json(output_dir, simulation_nodes):
    """Write simulation results to JSON in format compatible with Plotter.
    
    Args:
        output_dir: Directory to write JSON file
        simulation_nodes: List of FrictionSimulationData nodes with results
    """
    import json
    
    # Group simulations by material and organize hierarchically
    data_structure = {}
    metadata = {
        'materials': set(),
        'layers': set(),
        'forces_and_angles': {},
        'speeds': set(),
        'fields': ['time', 'nf', 'lfx', 'lfy', 'lateral_force', 'cof', 
                  'comx', 'comy', 'comz']
    }
    
    for sim_node in simulation_nodes:
        # Get linked results node
        results = sim_node.get_results() if hasattr(sim_node, 'get_results') else None
        if not results:
            continue
        
        material = sim_node.material.replace('-', '_')
        layers = sim_node.layers
        force = sim_node.force
        angle = sim_node.scan_angle
        speed = sim_node.scan_speed
        
        # Build nested structure
        mat_data = data_structure.setdefault(material, {})
        layer_data = mat_data.setdefault(f'l{layers}', {})
        speed_data = layer_data.setdefault(f's{int(speed*100)}', {})
        force_data = speed_data.setdefault(f'f{force}', {})
        
        # Get time series and convert to list format
        ts = results.time_series
        force_data[f'a{int(angle)}'] = {
            field: ts.get(field, []) for field in metadata['fields'] if field in ts
        }
        
        # Update metadata
        metadata['materials'].add(material)
        metadata['layers'].add(layers)
        metadata['speeds'].add(int(speed*100))
        if force not in metadata['forces_and_angles']:
            metadata['forces_and_angles'][force] = set()
        metadata['forces_and_angles'][force].add(int(angle))
    
    # Convert sets to lists
    for key in ['materials', 'layers', 'speeds']:
        metadata[key] = sorted(list(metadata[key]))
    metadata['forces_and_angles'] = {
        f: sorted(list(angles)) for f, angles in metadata['forces_and_angles'].items()
    }
    
    # Write to JSON file
    output_file = output_dir / 'output_full_100x100y.json'
    output_data = {
        'metadata': metadata,
        'results': data_structure
    }
    
    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    log.debug(f"Wrote {len(simulation_nodes)} results to {output_file}")

# =============================================================================
# DEFAULT SETTINGS
# =============================================================================

# MATLAB gem12 color palette (12 distinct colors for line plots)
GEM12_COLORS = [
    '#0072BD',  # Blue
    '#D95319',  # Orange
    '#EDB120',  # Yellow/Gold
    '#7E2F8E',  # Purple
    '#77AC30',  # Green
    '#4DBEEE',  # Light Blue
    '#A2142F',  # Dark Red
    '#FFD60A',  # Pink
    '#6582FD',  # Olive Green
    '#FF453A',  # Teal
    '#00A3A3',  # Lavender
    '#CB845D',  # Dark Cyan
]

DEFAULT_SETTINGS = {
    "figure": {"size": [10, 7], "dpi": 150},
    "fonts": {"title": 26, "axis_label": 24, "tick_label": 22, "legend": 16},
    "colors": {"palette": "gem12"},
    "markers": {"style": "o", "size": 12},
    "lines": {"width": 1.3, "fit_style": "--", "fit_alpha": 0.8},
    "grid": {"show": True, "which": "both", "major_style": "-", "minor_style": ":", 
             "major_alpha": 0.5, "minor_alpha": 0.3},
    "error_bands": {"alpha": 0.2},
    "legend": {"location": "best"},
    "layout": {},
    "axes": {"use_scientific_notation": True, "scilimits": [-3, 3]},
    "export": {"formats": ["png"], "transparent": True}
}

# =============================================================================
# PLOTTER CLASS
# =============================================================================

class Plotter:
    def __init__(self, data_dirs, labels, output_dir, settings=None):
        self.data_dirs = data_dirs
        self.labels = labels
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        # Load settings (use defaults if not provided)
        self.settings = DEFAULT_SETTINGS.copy()
        if settings:
            self._deep_merge_dict(self.settings, settings)
        
        # Apply settings
        self.figure_size = tuple(self.settings["figure"]["size"])
        self.time_step_fs = 1.0

        # Data storage
        self.full_data_files = {label: {} for label in self.labels}
        self.metadata = {}
        self.summary_df_cache = None
        self.material_type_map = {}
        
        # Display name mapping for material types
        self.type_display_names = {
            'b_type': 'buckled',
            'h_type': 'hexagonal',
            't_type': 'trigonal',
            'p_type': 'puckered',
            'other': 'bi-buckled'
        }

        self._discover_data_files()
        self._load_all_metadata()
        self._create_material_type_map()

    @classmethod
    def from_database(cls, query, labels, output_dir, settings=None):
        """Create Plotter instance from AiiDA database query.
        
        This method queries the AiiDA database and transforms results into
        the same format as directory-based data, ensuring all plotting
        methods work identically regardless of data source.
        
        Args:
            query: Dictionary with query parameters (material, layers, force, etc.)
            labels: List of labels for datasets (must match query structure)
            output_dir: Output directory for plots
            settings: Optional plot settings
            
        Returns:
            Configured Plotter instance
            
        Example:
            plotter = Plotter.from_database(
                query={'material': 'h-MoS2', 'layers': [1, 2]},
                labels=['1 Layer', '2 Layers'],
                output_dir='plots'
            )
        """
        try:
            from src.aiida import AIIDA_AVAILABLE
            if not AIIDA_AVAILABLE:
                raise ImportError("AiiDA not available. Install with: "
                                "conda install -c conda-forge aiida-core")
            
            from src.aiida.query import Friction2DDB
        except ImportError as e:
            log.error(f"Cannot use database plotting: {e}")
            raise
        
        # Create temporary directory structure for compatibility
        import tempfile
        temp_dir = Path(tempfile.mkdtemp(prefix='friction2d_'))
        data_dirs = []
        
        db = Friction2DDB()
        results = db.query(**query)
        
        log.info(f"Found {results.total_count} results from database")
        
        # Transform database results into directory-like structure
        for i, (label, sim_nodes) in enumerate(zip(labels, _partition_results(results, len(labels)))):
            label_dir = temp_dir / f"dataset_{i}"
            label_dir.mkdir(parents=True)
            
            # Create JSON file compatible with Plotter's expected format
            _write_results_to_json(label_dir, sim_nodes)
            data_dirs.append(str(label_dir))
        
        # Create plotter with transformed data
        plotter = cls(data_dirs, labels, output_dir, settings)
        plotter._is_temp_data = True
        plotter._temp_dir = temp_dir
        
        return plotter
    
    def __del__(self):
        """Clean up temporary files if created from database."""
        if hasattr(self, '_is_temp_data') and self._is_temp_data:
            import shutil
            if hasattr(self, '_temp_dir') and self._temp_dir.exists():
                shutil.rmtree(self._temp_dir, ignore_errors=True)

    # =========================================================================
    # INITIALIZATION HELPERS
    # =========================================================================

    def _deep_merge_dict(self, d1, d2):
        """Recursively merges d2 into d1."""
        for k, v in d2.items():
            if k in d1 and isinstance(d1[k], dict) and isinstance(v, dict):
                self._deep_merge_dict(d1[k], v)
            elif k in d1 and isinstance(d1[k], list) and isinstance(v, list):
                d1[k].extend(v)
            else:
                d1[k] = v

    def _create_material_type_map(self):
        """Creates a map from material_id to material_type from metadata."""
        material_types_dict = self.metadata.get('material_types')
        if isinstance(material_types_dict, dict):
            self.material_type_map = {
                material_id.strip(): type_name.strip()
                for type_name, material_list in material_types_dict.items()
                for material_id in material_list
            }
        else:
            log.warning("'material_types' not found in metadata. Plotting by type may fail.")

    def _discover_data_files(self):
        """Finds all output_full_*.json files in each data directory."""
        for label, data_dir in zip(self.labels, self.data_dirs):
            search_dir = os.path.join(data_dir, 'outputs')
            
            if not os.path.isdir(search_dir):
                log.debug(f"'outputs' not found in {data_dir}, searching base directory.")
                search_dir = data_dir
            
            if not os.path.isdir(search_dir):
                log.error(f"Data directory not found for label '{label}': {data_dir}")
                continue

            for filename in os.listdir(search_dir):
                match = re.match(r'output_full_(.+)\.json', filename)
                if match:
                    file_key = match.group(1)
                    self.full_data_files[label][file_key] = os.path.join(search_dir, filename)
            
            if not self.full_data_files[label]:
                log.warning(f"No 'output_full_*.json' files found for label '{label}'")

    def _load_all_metadata(self):
        """Loads and merges metadata from all available data files."""
        for label in self.labels:
            if not self.full_data_files[label]:
                continue
            for file_key in self.full_data_files[label]:
                _, metadata = self._load_full_data(label, file_key)
                if metadata:
                    self._deep_merge_dict(self.metadata, metadata)

    def _load_full_data(self, label, file_key):
        """Loads a single data file and returns (results, metadata)."""
        file_path = self.full_data_files.get(label, {}).get(file_key)
        if not file_path:
            log.debug(f"No data file found for label '{label}' and file_key '{file_key}'")
            return None, None
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            return data.get('results', {}), data.get('metadata', {})
        except (IOError, json.JSONDecodeError) as e:
            log.error(f"Loading data from {file_path}: {e}")
            return None, None

    # =========================================================================
    # DATA EXTRACTION
    # =========================================================================

    def _extract_all_runs(self, label, file_key):
        """Yields a dictionary for each simulation run found in the data file."""
        results, _ = self._load_full_data(label, file_key)
        if not results:
            return

        def process_level(data_dict, params_so_far):
            if 'columns' in data_dict and 'data' in data_dict:
                df = pd.DataFrame(data_dict['data'], columns=data_dict['columns'])
                df = self._add_derived_columns(df)
                run_data = params_so_far.copy()
                run_data['df'] = df
                yield run_data
                return
            
            for key, value in data_dict.items():
                if isinstance(value, dict):
                    new_params = params_so_far.copy()
                    if 'id' not in new_params:
                        new_params['id'] = key.strip()
                    else:
                        # Parse parameter prefixes (f=force, a=angle, etc.)
                        match_prefix = re.match(r'([a-zA-Z]+)(\d+\.?\d*)', key)
                        if match_prefix:
                            prefix, val_str = match_prefix.groups()
                            val = float(val_str)
                            param_map = {'f': 'force', 'a': 'angle', 'r': 'tip_radius', 'l': 'layer', 's': 'speed'}
                            if prefix in param_map:
                                new_params[param_map[prefix]] = val
                        # Parse suffix formats
                        if match := re.match(r'(\d+\.?\d*)nN', key):
                            new_params['force'] = float(match.group(1))
                        if match := re.match(r'(\d+\.?\d*)deg', key):
                            new_params['angle'] = float(match.group(1))
                    yield from process_level(value, new_params)
        
        yield from process_level(results, {})

    def _add_derived_columns(self, df):
        """Adds derived quantities (lf, cof, tip_sep) to a DataFrame."""
        if 'lfx' in df.columns and 'lfy' in df.columns:
            df['lf'] = np.sqrt(df['lfx']**2 + df['lfy']**2)

        if 'lf' in df.columns and 'nf' in df.columns:
            # COF = |lateral force| / |normal force|, always positive
            df['cof'] = (np.abs(df['lf']) / np.abs(df['nf'])).replace([np.inf, -np.inf], np.nan)

        if 'tipz' in df.columns and 'comz' in df.columns:
            df['tip_sep'] = df['tipz'] - df['comz']
        
        if all(c in df.columns for c in ['tipx', 'tipy', 'time']):
            time_diff_s = (df['time'].diff() * self.time_step_fs * 1e-15).fillna(0)
            dist_diff_A = np.sqrt(df['tipx'].diff().fillna(0)**2 + df['tipy'].diff().fillna(0)**2)
            df['tipspeed'] = (dist_diff_A * 1e-10 / time_diff_s).replace([np.inf, -np.inf], 0)
        
        return df

    # =========================================================================
    # SUMMARY DATA
    # =========================================================================

    def _get_summary_data_df(self):
        """Returns the summary DataFrame, calculating if not cached."""
        if self.summary_df_cache is None:
            self._calculate_summary_statistics()
        return self.summary_df_cache

    def _calculate_summary_statistics(self):
        """Calculates summary statistics for all runs."""
        log.info("Calculating summary statistics...")
        all_records = []
        
        for label in self.full_data_files.keys():
            for file_key in self.full_data_files[label].keys():
                for run_data in self._extract_all_runs(label, file_key):
                    df = run_data.pop('df')
                    summary_stats = df.mean().to_dict()
                    record = {
                        'dataset_label': label,
                        'file_key': file_key,
                        **run_data,
                        **summary_stats
                    }
                    all_records.append(record)

        self.summary_df_cache = pd.DataFrame(all_records)

        if not self.summary_df_cache.empty and 'id' in self.summary_df_cache.columns:
            self.summary_df_cache['material_type'] = self.summary_df_cache['id'].map(self.material_type_map)
            if 'size' not in self.summary_df_cache.columns:
                self.summary_df_cache['size'] = self.summary_df_cache['file_key'].str.extract(r'(\d+x\d+y?)')[0]

        log.debug(f"Summary DataFrame created with shape {self.summary_df_cache.shape}")
        log.debug(f"Columns: {self.summary_df_cache.columns.tolist()}")

    # =========================================================================
    # FILTERING
    # =========================================================================

    def _apply_default_filters(self, df, plot_config, x_col=None):
        """
        Applies default filters based on data availability.
        Returns the filters dict with defaults applied.
        """
        filters = {
            'angle': plot_config.get('angle'),
            'force': plot_config.get('force'),
            'size': plot_config.get('filter_size'),
            'layer': plot_config.get('filter_layer'),
            'speed': plot_config.get('filter_speed'),
            'tip_radius': plot_config.get('filter_tip_radius'),
        }
        
        # Default layer to 1 if available
        if filters['layer'] is None and 'layer' in df.columns:
            unique_layers = df['layer'].dropna().unique()
            if 1 in unique_layers:
                log.debug("Defaulting to layer 1")
                filters['layer'] = 1
        
        # Default angle to 0 when plotting vs force
        if x_col == 'force' and filters['angle'] is None:
            log.debug("Defaulting to angle 0.0 for force plot")
            filters['angle'] = 0.0
        
        return filters

    def _apply_filters(self, df, filters):
        """Applies filters to a DataFrame and returns the filtered result."""
        for key, value in filters.items():
            if value is not None and key in df.columns:
                original_len = len(df)
                if isinstance(value, list):
                    df = df[df[key].isin(value)]
                else:
                    df = df[df[key] == value]
                log.debug(f"Filter '{key}' == '{value}': {original_len} -> {len(df)}")
        return df

    def _apply_range_filters(self, df, plot_config):
        """Applies range-based filters (e.g., filter_force_range)."""
        force_range = plot_config.get('filter_force_range')
        if force_range and len(force_range) == 2 and 'force' in df.columns:
            original_len = len(df)
            df = df[(df['force'] >= force_range[0]) & (df['force'] <= force_range[1])]
            log.debug(f"Force range filter [{force_range[0]}, {force_range[1]}]: {original_len} -> {len(df)}")
        return df

    def _apply_material_filter(self, df, plot_config, plot_by):
        """Applies material/type filters based on plot_by mode."""
        filter_materials = plot_config.get('filter_materials')
        if not filter_materials:
            return df
        
        filter_values = [v.strip() for v in filter_materials]
        original_len = len(df)
        
        if plot_by == 'id' or plot_by == 'id_angle':
            escaped = [re.escape(v) for v in filter_values]
            pattern = '|'.join([f'(?:^|_){v}(?:_|$)' for v in escaped])
            df = df[df['id'].str.contains(pattern, regex=True)]
        elif plot_by == 'material_type':
            ids_to_plot = [mid for mid, mtype in self.material_type_map.items() if mtype in filter_values]
            df = df[df['id'].isin(ids_to_plot)]
        
        log.debug(f"Material filter: {original_len} -> {len(df)}")
        return df

    def _remove_outliers(self, df, x_col, y_col, threshold=10.0):
        """Removes outliers based on magnitude relative to median."""
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
        
        cleaned_df = df.groupby(x_col).apply(remove_magnitude_outliers, include_groups=False).reset_index()
        
        removed = initial_rows - len(cleaned_df)
        if removed > 0:
            log.debug(f"Removed {removed} outlier points")
        
        return cleaned_df

    # =========================================================================
    # LINEAR FIT
    # =========================================================================

    def _calculate_linear_fit(self, x_data, y_data, x_range=None):
        """
        Calculates linear regression constrained to pass through the first data point.
        Uses proper constrained regression .
        Returns fit parameters or None if insufficient data.
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
        
        # Get the first point (origin for constrained fit)
        x_origin, y_origin = x_clean[0], y_clean[0]
        
        # Translate data so first point is at origin
        x_shifted = x_clean - x_origin
        y_shifted = y_clean - y_origin
        
        # Constrained regression through origin: slope = sum(x*y) / sum(x^2)
        slope = np.sum(x_shifted * y_shifted) / np.sum(x_shifted**2)
        intercept = y_origin - slope * x_origin  # Intercept in original coordinates
        
        # Calculate predictions and residuals
        y_pred = slope * x_clean + intercept
        residuals = y_clean - y_pred
        rmse = np.sqrt(np.mean(residuals**2))
        
        # R-squared calculation
        ss_res = np.sum(residuals**2)
        ss_tot = np.sum((y_clean - np.mean(y_clean))**2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        # Standard error of slope for constrained regression through origin
        n = len(x_clean)
        if n > 1:
            mse = ss_res / (n - 1)  # Only 1 parameter (slope) estimated
            slope_stderr = np.sqrt(mse / np.sum(x_shifted**2))
        else:
            slope_stderr = 0
        
        # Standard error of intercept (derived from slope uncertainty)
        se_intercept = slope_stderr * np.abs(x_origin)
        
        return {
            'slope': slope,
            'intercept': intercept,
            'slope_stderr': slope_stderr,
            'intercept_stderr': se_intercept,
            'r_squared': r_squared,
            'rmse': rmse
        }

    # =========================================================================
    # PLOTTING HELPERS
    # =========================================================================

    def _plot_series(self, ax, x_data, y_data, label, plot_style, add_fit, fit_x_range, 
                        std_data=None, show_error_bands=True, color_idx=0):
        """
        Plots a single data series with optional fit and error bands.
        Returns the line color used.
        """
        s = self.settings
        marker = s["markers"]["style"]
        
        # Get color from gem12 palette or fallback
        palette = s["colors"].get("palette", "gem12")
        if palette == "gem12":
            color = GEM12_COLORS[color_idx % len(GEM12_COLORS)]
        else:
            color = None  # Let matplotlib choose
        
        if plot_style == 'scatter':
            scatter = ax.scatter(x_data, y_data, label=label, s=s["markers"]["size"]**2, 
                                color=color)
            if color is None:
                color = scatter.get_facecolors()[0]
        else:
            linestyle = '' if add_fit else '-'
            line = ax.plot(x_data, y_data, marker=marker, linestyle=linestyle, 
                            linewidth=s["lines"]["width"], label=label, color=color,
                            markersize=s["markers"]["size"])
            if color is None:
                color = line[0].get_color()

        # Add error bands if std data provided AND show_error_bands is True
        if std_data is not None and show_error_bands:
            # Clip lower bound to 0 to prevent negative error bands (e.g., for COF)
            lower_bound = np.maximum(y_data - std_data, 0)
            upper_bound = y_data + std_data
            ax.fill_between(x_data, lower_bound, upper_bound,
                            alpha=s["error_bands"]["alpha"], color=color)

        # Add linear fit if requested
        if add_fit:
            fit_params = self._calculate_linear_fit(np.array(x_data), np.array(y_data), fit_x_range)
            if fit_params:
                x_min = fit_x_range[0] if fit_x_range else x_data.min()
                x_max = fit_x_range[1] if fit_x_range else x_data.max()
                x_fit = np.linspace(x_min, x_max, 100)
                y_fit = fit_params['slope'] * x_fit + fit_params['intercept']
                ax.plot(x_fit, y_fit, s["lines"]["fit_style"], 
                       alpha=s["lines"]["fit_alpha"], linewidth=s["lines"]["width"], color=color)
        
        return color

    def _finalize_plot(self, ax, plot_config, x_col, y_col):
        """Applies final formatting to a plot (MATLAB-style)."""
        s = self.settings
        
        ax.set_xlabel(plot_config.get('x_label', x_col), fontsize=s["fonts"]["axis_label"])
        ax.set_ylabel(plot_config.get('y_label', y_col), fontsize=s["fonts"]["axis_label"])
        ax.tick_params(axis='both', which='major', labelsize=s["fonts"]["tick_label"])
        
        # Scientific notation for tick labels (applies offset like ×10⁻³)
        axes_config = s.get("axes", {})
        use_sci = plot_config.get('use_scientific_notation', axes_config.get('use_scientific_notation', False))
        if use_sci:
            scilimits = axes_config.get('scilimits', [-2, 2])
            ax.ticklabel_format(style='sci', axis='both', scilimits=tuple(scilimits), useMathText=True)
            # Make the exponent (×10⁻²) the same size as tick labels
            ax.xaxis.get_offset_text().set_fontsize(s["fonts"]["tick_label"])
            ax.yaxis.get_offset_text().set_fontsize(s["fonts"]["tick_label"])
        
        title = plot_config.get('title')
        if title:
            ax.set_title(title, fontsize=s["fonts"]["title"])
        
        # MATLAB-style grid with minor gridlines
        grid_config = s.get("grid", {})
        if grid_config.get("show", True):
            which = grid_config.get("which", "both")
            if which in ["major", "both"]:
                ax.grid(True, which='major', linestyle=grid_config.get("major_style", "-"),
                       alpha=grid_config.get("major_alpha", 0.5))
            if which in ["minor", "both"]:
                ax.minorticks_on()
                ax.grid(True, which='minor', linestyle=grid_config.get("minor_style", ":"),
                       alpha=grid_config.get("minor_alpha", 0.3))
        
        if ax.get_legend_handles_labels()[1]:
            ax.legend(loc=s["legend"]["location"], fontsize=s["fonts"]["legend"])

    def _save_plot(self, fig, filename):
        """Saves the plot to file(s) in multiple formats if configured."""
        if not filename:
            log.warning("No filename specified. Plot not saved.")
            plt.close(fig)
            return
        
        export_config = self.settings.get("export", {})
        formats = export_config.get("formats", ["png"])
        transparent = export_config.get("transparent", False)
        
        # Get base filename without extension
        base_name = os.path.splitext(filename)[0]
        original_ext = os.path.splitext(filename)[1].lstrip('.')
        
        # Always save the originally requested format
        if original_ext and original_ext not in formats:
            formats = [original_ext] + list(formats)
        
        # Fixed margins to ensure all axis labels and tick labels are visible
        # while maximizing plot area. All plots use the same margins for
        # consistent sizing in LaTeX.
        #
        # Figure size: 10 x 7 inches
        # Left: y-axis label (24pt) + tick labels (22pt, max 5 chars) ≈ 1.3 in → 0.13
        # Bottom: x-axis label (24pt) + tick labels (22pt) ≈ 0.9 in → 0.13
        # Right/Top: minimal padding
        
        try:
            fig.subplots_adjust(
                left=0.13,
                bottom=0.13,
                right=0.97,
                top=0.97
            )
        except Exception as e:
            log.warning(f"subplots_adjust failed: {e}")

        for fmt in formats:
            output_path = os.path.join(self.output_dir, f"{base_name}.{fmt}")
            # Removed bbox_inches='tight' to ensure consistent image dimensions for LaTeX
            fig.savefig(output_path, dpi=self.settings["figure"]["dpi"], 
                       format=fmt, transparent=transparent)
            log.info(f"Generated plot: {output_path}")
        
        plt.close(fig)

    # =========================================================================
    # SUMMARY PLOT
    # =========================================================================

    def _generate_summary_plot(self, plot_config):
        """Generates a summary plot (main plot type)."""
        summary_df = self._get_summary_data_df()
        if summary_df.empty:
            log.warning("Summary data is empty. Skipping plot.")
            return

        title = plot_config.get('title', '(no title)')
        log.debug(f"Generating plot: {title}")

        # Filter by datasets
        df = summary_df.copy()
        datasets = plot_config.get('datasets')
        if datasets:
            df = df[df['dataset_label'].isin(datasets)]
            log.debug(f"Dataset filter: {len(summary_df)} -> {len(df)}")

        # Get plot configuration
        plot_by = plot_config.get('plot_by', 'id')
        plot_style = plot_config.get('plot_style', 'line')
        x_col = plot_config['x_axis']
        y_col = plot_config['y_axis']
        add_fit = plot_config.get('add_linear_fit', False)
        fit_x_range = plot_config.get('fit_x_range')
        show_dataset = plot_config.get('show_dataset_in_legend', False)
        show_error_bands = plot_config.get('show_error_bands', True)  # Optional error bands

        # Apply filters
        filters = self._apply_default_filters(df, plot_config, x_col)
        df = self._apply_filters(df, filters)
        df = self._apply_range_filters(df, plot_config)
        df = self._apply_material_filter(df, plot_config, plot_by)

        if df.empty:
            log.warning("No data left after filtering. Skipping plot.")
            return

        if y_col not in df.columns:
            log.error(f"y-axis column '{y_col}' not found in data. Skipping.")
            return

        # Remove outliers
        df = self._remove_outliers(df, x_col, y_col)
        if df.empty:
            log.warning("No data left after outlier removal. Skipping.")
            return

        # Create figure
        fig, ax = plt.subplots(figsize=self.figure_size)

        # Determine grouping column and whether to aggregate
        if plot_by == 'dataset_label':
            group_col = 'dataset_label'
            aggregate = True
        elif plot_by == 'material_type':
            group_col = 'material_type'
            aggregate = True
        elif plot_by == 'id_angle':
            group_col = ['id', 'angle']
            aggregate = False
        else:  # plot_by == 'id'
            group_col = 'id'
            aggregate = False

        # Plot each group
        color_idx = 0
        for group_name, group in df.groupby(group_col):
            # Determine label
            if plot_by == 'material_type':
                label = self.type_display_names.get(group_name, group_name)
            elif plot_by == 'id_angle':
                # group_name is a tuple (id, angle)
                label = f"{group_name[0]}_{int(group_name[1])}"
            elif show_dataset and 'dataset_label' in group.columns:
                dataset = group['dataset_label'].iloc[0]
                label = f"{group_name} ({dataset})"
            else:
                label = group_name
            
            if aggregate:
                # Calculate mean and std for each x value
                plot_data = group.groupby(x_col)[y_col].agg(['mean', 'std']).reset_index()
                plot_data = plot_data.sort_values(by=x_col)
                self._plot_series(ax, plot_data[x_col], plot_data['mean'], label, 
                                 plot_style, add_fit, fit_x_range, plot_data['std'],
                                 show_error_bands=show_error_bands, color_idx=color_idx)
            else:
                # Plot raw data points
                group = group.sort_values(by=x_col)
                self._plot_series(ax, group[x_col], group[y_col], label,
                                 plot_style, add_fit, fit_x_range,
                                 show_error_bands=show_error_bands, color_idx=color_idx)
            
            log.debug(f"Plotted {group_name} ({len(group)} points)")
            color_idx += 1

        # Set y-axis limits based on data
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

        # Override with explicit y_limits if specified
        y_limits = plot_config.get('y_limits')
        if y_limits:
            if y_limits[0] is not None:
                ax.set_ylim(bottom=y_limits[0])
            if len(y_limits) > 1 and y_limits[1] is not None:
                ax.set_ylim(top=y_limits[1])

        # Override with explicit x_limits if specified
        x_limits = plot_config.get('x_limits')
        if x_limits:
            if x_limits[0] is not None:
                ax.set_xlim(left=x_limits[0])
            if len(x_limits) > 1 and x_limits[1] is not None:
                ax.set_xlim(right=x_limits[1])

        self._finalize_plot(ax, plot_config, x_col, y_col)
        self._save_plot(fig, plot_config.get('filename'))

    # =========================================================================
    # SCATTER COMPARISON PLOT
    # =========================================================================

    def _generate_scatter_comparison(self, plot_config):
        """
        Generates a scatter plot comparing two data sources.
        
        Supports:
        - External JSON file for x-axis data (e.g., tribology index)
        - Force range averaging with fit-based error bars
        - Iterative outlier removal
        - R² display and material labels
        """
        x_source = plot_config.get('x_source', {})
        y_source = plot_config.get('y_source', {})
        
        if not x_source or not y_source:
            log.error("scatter_comparison requires 'x_source' and 'y_source'")
            return
        
        summary_df = self._get_summary_data_df()
        
        # Load external JSON file data
        def load_external_json(source_config):
            """Load data from external JSON file with materials mapping."""
            file_path = source_config.get('file')
            if not file_path:
                return None, None, None
            
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                materials = data.get(source_config.get('material_column', 'materials'), [])
                values = np.array(data.get(source_config.get('value_column', 'tribIndex'), []))
                errors = np.array(data.get(source_config.get('error_column', 'dev'), []))
                
                return materials, values, errors
            except Exception as e:
                log.error(f"Loading external JSON file {file_path}: {e}")
                return None, None, None
        
        def get_aggregated_source_data(source_config, material_list=None):
            """
            Extract data with optional force range averaging.
            Returns: (materials, values, errors) arrays
            """
            dataset = source_config.get('dataset')
            metric = source_config.get('metric')
            
            if not dataset or not metric:
                log.error("Source must specify 'dataset' and 'metric'")
                return None, None, None
            
            df = summary_df[summary_df['dataset_label'] == dataset].copy()
            
            # Apply basic filters
            for key in ['filter_layer', 'filter_size']:
                value = source_config.get(key)
                col = key.replace('filter_', '')
                if value is not None and col in df.columns:
                    df = df[df[col] == value]
            
            # Apply angle filter (can be single value or list of values)
            angle = source_config.get('angle')
            if angle is not None and 'angle' in df.columns:
                if isinstance(angle, list):
                    df = df[df['angle'].isin(angle)]
                else:
                    df = df[df['angle'] == angle]
            
            # Filter to only materials in material_list if provided
            if material_list is not None and 'id' in df.columns:
                # Match materials flexibly (handle prefixes like h_, t_, etc.)
                matched_ids = []
                for mat in material_list:
                    for df_id in df['id'].unique():
                        # Check if material name matches (with or without type prefix)
                        if mat in df_id or df_id in mat or mat.replace('_', '') in df_id.replace('_', ''):
                            matched_ids.append(df_id)
                df = df[df['id'].isin(matched_ids)]
            
            if df.empty:
                log.warning(f"No data found for source: {source_config}")
                return None, None, None
            
            # Check for force range averaging
            force_range = source_config.get('force_range')
            error_metric = source_config.get('error_metric', 'slope_stderr')  # slope_stderr, rmse, or r_squared
            
            materials_out = []
            values_out = []
            errors_out = []
            
            for mat_id in df['id'].unique():
                mat_df = df[df['id'] == mat_id].copy()
                
                if force_range and len(force_range) == 2:
                    # Filter to force range
                    mat_df = mat_df[(mat_df['force'] >= force_range[0]) & 
                                   (mat_df['force'] <= force_range[1])]
                    
                    if len(mat_df) < 2:
                        continue
                    
                    # Calculate average value
                    avg_value = mat_df[metric].mean()
                    
                    # Calculate error from linear fit
                    fit = self._calculate_linear_fit(
                        mat_df['force'].values, 
                        mat_df[metric].values
                    )
                    
                    if fit:
                        if error_metric == 'slope_stderr':
                            error = fit['slope_stderr']
                        elif error_metric == 'rmse':
                            error = fit['rmse']
                        elif error_metric == 'r_squared':
                            error = 1 - fit['r_squared']  # Invert so lower is better
                        else:
                            error = fit['slope_stderr']
                    else:
                        error = mat_df[metric].std()
                    
                    materials_out.append(mat_id)
                    values_out.append(avg_value)
                    errors_out.append(error)
                else:
                    # No force range - use single force value or all data
                    force = source_config.get('force')
                    if force is not None:
                        mat_df = mat_df[mat_df['force'] == force]
                    
                    if mat_df.empty:
                        continue
                    
                    materials_out.append(mat_id)
                    values_out.append(mat_df[metric].mean())
                    errors_out.append(mat_df[metric].std() if len(mat_df) > 1 else 0)
            
            return materials_out, np.array(values_out), np.array(errors_out)
        
        def iterative_outlier_removal(x, y, x_err, y_err, materials, num_remove):
            """Iteratively removes points with largest residuals from OLS fit."""
            x = np.array(x)
            y = np.array(y)
            x_err = np.array(x_err) if x_err is not None else np.zeros_like(x)
            y_err = np.array(y_err) if y_err is not None else np.zeros_like(y)
            materials = list(materials)
            removed = []
            
            for _ in range(min(num_remove, len(x) - 2)):
                if len(x) <= 2:
                    break
                
                # Fit OLS
                slope, intercept, _, _, _ = stats.linregress(x, y)
                y_pred = slope * x + intercept
                residuals = np.abs(y - y_pred)
                
                # Find largest residual
                max_idx = np.argmax(residuals)
                removed.append(materials[max_idx])
                
                # Remove point
                mask = np.ones(len(x), dtype=bool)
                mask[max_idx] = False
                x = x[mask]
                y = y[mask]
                x_err = x_err[mask]
                y_err = y_err[mask]
                materials = [m for i, m in enumerate(materials) if mask[i]]
            
            if removed:
                log.info(f"Outlier removal: removed {len(removed)} points: {removed}")
            
            return x, y, x_err, y_err, materials
        
        # === Main logic ===
        
        # Check if x_source is external file
        if 'file' in x_source:
            x_materials, x_data, x_errors = load_external_json(x_source)
            if x_materials is None:
                return
            
            # Get y data, filtered to x_materials
            y_materials, y_data, y_errors = get_aggregated_source_data(y_source, x_materials)
            if y_materials is None:
                return
            
            # Match materials between x and y
            matched_x, matched_y = [], []
            matched_x_err, matched_y_err = [], []
            matched_materials = []
            
            for i, x_mat in enumerate(x_materials):
                for j, y_mat in enumerate(y_materials):
                    # Flexible matching
                    if (x_mat in y_mat or y_mat in x_mat or 
                        x_mat.replace('_', '') in y_mat.replace('_', '')):
                        matched_x.append(x_data[i])
                        matched_y.append(y_data[j])
                        matched_x_err.append(x_errors[i] if len(x_errors) > i else 0)
                        matched_y_err.append(y_errors[j] if len(y_errors) > j else 0)
                        matched_materials.append(x_mat)
                        break
            
            x_data = np.array(matched_x)
            y_data = np.array(matched_y)
            x_errors = np.array(matched_x_err)
            y_errors = np.array(matched_y_err)
            materials = matched_materials
        else:
            # Both sources from datasets
            x_materials, x_data, x_errors = get_aggregated_source_data(x_source)
            y_materials, y_data, y_errors = get_aggregated_source_data(y_source, x_materials)
            
            if x_data is None or y_data is None:
                log.error("Could not extract data for scatter comparison")
                return
            
            materials = x_materials if x_materials else []
            if x_errors is None:
                x_errors = np.zeros_like(x_data)
            if y_errors is None:
                y_errors = np.zeros_like(y_data)
        
        if len(x_data) == 0 or len(y_data) == 0:
            log.error("No matched data points for scatter comparison")
            return
        
        if len(x_data) != len(y_data):
            log.warning(f"Data size mismatch: x={len(x_data)}, y={len(y_data)}. Using minimum.")
            min_len = min(len(x_data), len(y_data))
            x_data = x_data[:min_len]
            y_data = y_data[:min_len]
            x_errors = x_errors[:min_len]
            y_errors = y_errors[:min_len]
            materials = materials[:min_len]
        
        # Apply iterative outlier removal if requested
        num_outliers = plot_config.get('iterative_outlier_removal', 0)
        if num_outliers > 0:
            x_data, y_data, x_errors, y_errors, materials = iterative_outlier_removal(
                x_data, y_data, x_errors, y_errors, materials, num_outliers
            )
        
        # Create figure
        fig, ax = plt.subplots(figsize=self.figure_size)
        
        palette = self.settings["colors"].get("palette", "gem12")
        show_error_bars = plot_config.get('show_error_bars', False)
        color_by_class = plot_config.get('color_by_material_class', False)
        
        if color_by_class and materials:
            # Group materials by class (prefix like h_, t_, p_, b_)
            def get_material_class(mat_name):
                prefixes = {'h_': 'hexagonal', 't_': 'trigonal', 'p_': 'puckered', 'b_': 'buckled'}
                for prefix, class_name in prefixes.items():
                    if mat_name.startswith(prefix):
                        return class_name
                return 'bi-buckled'
            
            # Build class-to-indices mapping
            class_indices = {}
            for i, mat in enumerate(materials):
                mat_class = get_material_class(mat)
                if mat_class not in class_indices:
                    class_indices[mat_class] = []
                class_indices[mat_class].append(i)
            
            # Plot each class with its own color
            for class_idx, (class_name, indices) in enumerate(sorted(class_indices.items())):
                color = GEM12_COLORS[class_idx % len(GEM12_COLORS)] if palette == "gem12" else None
                
                class_x = x_data[indices]
                class_y = y_data[indices]
                class_x_err = x_errors[indices] if x_errors is not None else None
                class_y_err = y_errors[indices] if y_errors is not None else None
                
                if show_error_bars and ((class_x_err is not None and np.any(class_x_err > 0)) or 
                                         (class_y_err is not None and np.any(class_y_err > 0))):
                    ax.errorbar(class_x, class_y,
                               xerr=class_x_err if class_x_err is not None and np.any(class_x_err > 0) else None,
                               yerr=class_y_err if class_y_err is not None and np.any(class_y_err > 0) else None,
                               fmt='o', color=color, label=class_name,
                               markersize=self.settings["markers"]["size"],
                               capsize=3, capthick=1, elinewidth=1)
                else:
                    ax.scatter(class_x, class_y, s=self.settings["markers"]["size"]**2, 
                              color=color, label=class_name)
        else:
            # Original single-color plotting
            point_color = GEM12_COLORS[0] if palette == "gem12" else None
            
            if show_error_bars and (np.any(x_errors > 0) or np.any(y_errors > 0)):
                ax.errorbar(x_data, y_data, 
                           xerr=x_errors if np.any(x_errors > 0) else None,
                           yerr=y_errors if np.any(y_errors > 0) else None,
                           fmt='o', color=point_color, 
                           markersize=self.settings["markers"]["size"],
                           capsize=3, capthick=1, elinewidth=1)
            else:
                ax.scatter(x_data, y_data, s=self.settings["markers"]["size"]**2, color=point_color)
        
        # Add point labels if requested (labels with common identifier between x and y)
        if plot_config.get('show_point_labels', False) and materials:
            x_range = x_data.max() - x_data.min()
            dx = x_range * 0.01
            label_fontsize = plot_config.get('point_label_fontsize', 8)
            for i, mat in enumerate(materials):
                ax.text(x_data[i] + dx, y_data[i], mat, fontsize=label_fontsize)
        
        # Add y=x reference line if requested
        if plot_config.get('show_identity_line', False):
            lims = [min(x_data.min(), y_data.min()), max(x_data.max(), y_data.max())]
            ax.plot(lims, lims, '--', color='gray', alpha=0.5, label='y=x')
        
        # Calculate and display linear fit
        fit = None
        if plot_config.get('add_linear_fit', False):
            fit = self._calculate_linear_fit(x_data, y_data)
            if fit:
                x_fit = np.linspace(x_data.min() * 0.9, x_data.max() * 1.1, 100)
                y_fit = fit['slope'] * x_fit + fit['intercept']
                fit_color = GEM12_COLORS[1] if palette == "gem12" else 'red'
                ax.plot(x_fit, y_fit, '--', color=fit_color, alpha=0.8, 
                       linewidth=self.settings["lines"]["width"],
                       label=f"Fit (R²={fit['r_squared']:.4f})")
        
        # Display R² in corner if requested
        if plot_config.get('show_r_squared', False):
            if fit is None:
                fit = self._calculate_linear_fit(x_data, y_data)
            if fit:
                r2_text = f"R² = {fit['r_squared']:.4f}"
                if num_outliers > 0:
                    r2_text += f" (Filtered {num_outliers})"
                ax.text(0.05, 0.95, r2_text, transform=ax.transAxes,
                       fontsize=self.settings["fonts"]["legend"],
                       fontweight='bold', verticalalignment='top')
        
        # Labels
        x_label = plot_config.get('x_label', f"{x_source.get('dataset', 'X')} {x_source.get('metric', '')}")
        y_label = plot_config.get('y_label', f"{y_source.get('dataset', 'Y')} {y_source.get('metric', '')}")
        
        ax.set_xlabel(x_label, fontsize=self.settings["fonts"]["axis_label"])
        ax.set_ylabel(y_label, fontsize=self.settings["fonts"]["axis_label"])
        ax.tick_params(axis='both', which='major', labelsize=self.settings["fonts"]["tick_label"])
        
        # Scientific notation for tick labels (applies offset like ×10⁻³)
        axes_config = self.settings.get("axes", {})
        use_sci = plot_config.get('use_scientific_notation', axes_config.get('use_scientific_notation', False))
        if use_sci:
            scilimits = axes_config.get('scilimits', [-2, 2])
            ax.ticklabel_format(style='sci', axis='both', scilimits=tuple(scilimits), useMathText=True)
            # Make the exponent (×10⁻²) the same size as tick labels
            ax.xaxis.get_offset_text().set_fontsize(self.settings["fonts"]["tick_label"])
            ax.yaxis.get_offset_text().set_fontsize(self.settings["fonts"]["tick_label"])
        
        if plot_config.get('title'):
            ax.set_title(plot_config['title'], fontsize=self.settings["fonts"]["title"])
        
        # Legend (only if there are labeled items)
        if ax.get_legend_handles_labels()[1]:
            legend_loc = plot_config.get('legend_location', self.settings["legend"]["location"])
            ax.legend(fontsize=self.settings["fonts"]["legend"], loc=legend_loc)
        
        # Apply MATLAB-style grid
        grid_config = self.settings.get("grid", {})
        if grid_config.get("show", True):
            ax.grid(True, which='major', linestyle=grid_config.get("major_style", "-"),
                   alpha=grid_config.get("major_alpha", 0.5))
            ax.minorticks_on()
            ax.grid(True, which='minor', linestyle=grid_config.get("minor_style", ":"),
                   alpha=grid_config.get("minor_alpha", 0.3))
        
        # Apply axis limits if specified
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
        
        self._save_plot(fig, plot_config.get('filename'))

    # =========================================================================
    # TIMESERIES PLOT
    # =========================================================================

    def _generate_timeseries_plot(self, plot_config):
        """Generates a timeseries plot."""
        datasets = plot_config.get('datasets', [self.labels[0]] if self.labels else [])
        if not datasets:
            log.error("No dataset specified for timeseries plot.")
            return

        label = datasets[0]
        file_key = plot_config.get('filter_size')
        if not file_key:
            log.error("'filter_size' is required for timeseries plots.")
            return

        _, local_metadata = self._load_full_data(label, file_key)
        if not local_metadata:
            log.error(f"Could not load metadata for file_key '{file_key}'.")
            return
        
        time_series = local_metadata.get('time_series')
        if not time_series:
            log.error(f"'time_series' not found in metadata.")
            return

        all_runs = list(self._extract_all_runs(label, file_key))
        if not all_runs:
            log.warning(f"No runs found for label '{label}' and file_key '{file_key}'.")
            return

        # Build filters
        # Support filter_forces as a list of forces to show
        force_filter = None
        if not plot_config.get('plot_all_forces'):
            force_filter = plot_config.get('filter_forces') or plot_config.get('force')
        
        filters = {
            'id': plot_config.get('filter_materials'),
            'force': force_filter,
            'angle': plot_config.get('angle'),
            'layer': plot_config.get('filter_layer'),
            'speed': plot_config.get('filter_speed'),
            'tip_radius': plot_config.get('filter_tip_radius'),
        }
        
        # Apply defaults
        if filters['layer'] is None:
            layers = set(run.get('layer') for run in all_runs if 'layer' in run)
            if 1 in layers:
                filters['layer'] = 1
        
        # Only default angle to 0.0 if no angle filter is specified
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
            log.warning("No runs matched filters for timeseries plot.")
            return

        y_col = plot_config.get('y_axis')
        if not y_col:
            log.error("Missing y-axis for timeseries plot.")
            return

        fig, ax = plt.subplots(figsize=self.figure_size)
        
        # Use gem12 colors for timeseries
        palette = self.settings["colors"].get("palette", "gem12")
        
        for idx, run in enumerate(filtered_runs):
            df = run['df']
            if y_col not in df.columns:
                log.warning(f"y-axis '{y_col}' not found for run {run.get('id')}. Skipping.")
                continue

            label_parts = [run.get('id', 'N/A')]
            if 'force' in run:
                label_parts.append(f"F={run['force']}nN")
            
            color = GEM12_COLORS[idx % len(GEM12_COLORS)] if palette == "gem12" else None
            ax.plot(time_series, df[y_col], label=", ".join(label_parts), color=color,
                   linewidth=self.settings["lines"]["width"])

        self._finalize_plot(ax, plot_config, 'time', y_col)
        self._save_plot(fig, plot_config.get('filename'))

    # =========================================================================
    # CORRELATION PLOTS
    # =========================================================================

    def _generate_correlation_plots(self, plot_config):
        """Generates correlation heatmaps from friction ranking files."""
        log.info("Generating correlation plots...")
        
        ranking_files = glob.glob(os.path.join(self.output_dir, 'friction_ranking_*.json'))
        if not ranking_files:
            log.error("No friction_ranking_*.json files found.")
            return

        all_ranks = []
        for f_path in ranking_files:
            size_match = re.search(r'friction_ranking_(.+)\.json', os.path.basename(f_path))
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
                            'material': material_data['material'], 'rank': rank
                        })
        
        if not all_ranks:
            log.error("Could not parse ranking data.")
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
            log.error(f"Unknown correlation type '{correlate_by}'")

    def _plot_correlation_heatmap(self, rank_df, correlate_by, plot_config):
        """Generic correlation heatmap plotter."""
        if correlate_by == 'size':
            force = plot_config.get('correlation_force', 30)
            df = rank_df[rank_df['force'] == force]
            pivot_df = df.pivot_table(index='material', columns='size', values='rank', aggfunc='mean')
            title = f'Rank Correlation Across Sizes (Force={force}nN)'
            filename = plot_config.get('filename', f'rank_corr_by_size_f{force}.png')
        else:  # by force
            for size, group in rank_df.groupby('size'):
                pivot_df = group.pivot_table(index='material', columns='force', values='rank', aggfunc='mean')
                pivot_df.dropna(inplace=True)
                
                if len(pivot_df) < 2 or len(pivot_df.columns) < 2:
                    continue
                
                corr = pivot_df.corr(method='spearman')
                
                fig, ax = plt.subplots(figsize=(10, 8))
                sns.heatmap(corr, annot=True, cmap='crest', fmt='.2f', ax=ax)
                ax.set_title(f'Rank Correlation Across Forces (Size={size})')
                
                filename = plot_config.get('filename_prefix', 'rank_corr_by_force') + f'_{size}.png'
                self._save_plot(fig, filename)
            return
        
        pivot_df.dropna(inplace=True)
        if len(pivot_df) < 2:
            log.error("Not enough data for correlation matrix.")
            return
        
        corr = pivot_df.corr(method='spearman')
        
        fig, ax = plt.subplots(figsize=(8, 6))
        sns.heatmap(corr, annot=True, cmap='crest', fmt='.2f', ax=ax)
        ax.set_title(title)
        
        self._save_plot(fig, filename)

    def _plot_pairwise_correlation(self, rank_df, plot_config):
        """Plots force-vs-force correlation between two sizes."""
        sizes = plot_config.get('sizes_to_compare')
        if not sizes or len(sizes) != 2:
            log.error("'pairwise' requires 'sizes_to_compare' with two sizes.")
            return

        size1, size2 = sizes
        df1 = rank_df[rank_df['size'] == size1]
        df2 = rank_df[rank_df['size'] == size2]

        forces1 = sorted(df1['force'].unique())
        forces2 = sorted(df2['force'].unique())

        if not forces1 or not forces2:
            log.error(f"No force data for sizes: {size1}, {size2}")
            return

        corr_matrix = pd.DataFrame(index=forces2, columns=forces1, dtype=float)

        for f1 in forces1:
            for f2 in forces2:
                ranks1 = df1[df1['force'] == f1].groupby('material')['rank'].mean()
                ranks2 = df2[df2['force'] == f2].groupby('material')['rank'].mean()
                combined = pd.DataFrame({'r1': ranks1, 'r2': ranks2}).dropna()
                
                if len(combined) > 1:
                    corr_matrix.loc[f2, f1] = combined['r1'].corr(combined['r2'], method='spearman')

        fig, ax = plt.subplots(figsize=(12, 10))
        sns.heatmap(corr_matrix, annot=True, fmt='.2f', cmap='crest', 
                   cbar_kws={'label': "Spearman's Correlation"}, linewidths=.5, ax=ax)
        
        ax.set_title(f'Force vs Force Correlation ({size1} vs {size2})')
        ax.set_xlabel(f'Force (nN) for {size1}')
        ax.set_ylabel(f'Force (nN) for {size2}')
        
        filename = plot_config.get('filename', f'force_vs_force_corr_{size1}_vs_{size2}.png')
        self._save_plot(fig, filename)

    # =========================================================================
    # FRICTION RANKING
    # =========================================================================

    def rank_friction(self, plot_config):
        """Ranks materials by friction and exports to JSON."""
        log.info("Generating friction rankings...")
        
        summary_df = self._get_summary_data_df()
        if summary_df.empty:
            log.warning("Summary data is empty.")
            return

        metrics = plot_config.get('rank_by', ['lf'])
        if not isinstance(metrics, list):
            metrics = [metrics]

        # Apply layer filter
        df = summary_df.copy()
        layer = plot_config.get('filter_layer')
        if layer:
            df = df[df['layer'] == layer]

        # Filter by angle
        angle = plot_config.get('angle', 0)
        df = df[df['angle'] == angle]

        # Filter by force if specified
        force = plot_config.get('force')
        if force is not None:
            df = df[df['force'] == force]

        if df.empty:
            log.warning("No data available for ranking.")
            return

        fit_x_range = plot_config.get('fit_x_range')

        for metric in metrics:
            if metric not in df.columns:
                log.warning(f"Metric '{metric}' not found. Skipping.")
                continue
            
            rank_df = df[df[metric] > 0].copy()
            if rank_df.empty:
                continue

            agg_df = rank_df.groupby(['size', 'force', 'id'])[metric].mean().reset_index()

            for size, group in agg_df.groupby('size'):
                # Calculate fits
                fits = {}
                for mat_id, mat_group in group.groupby('id'):
                    fit = self._calculate_linear_fit(mat_group['force'].values, mat_group[metric].values, fit_x_range)
                    fits[mat_id] = fit

                # Rank by force
                ranks_by_force = {}
                for f, f_group in group.groupby('force'):
                    ranked = f_group.sort_values(metric, ascending=False).reset_index()
                    ranked['rank'] = ranked.index + 1
                    
                    materials = []
                    for _, row in ranked.iterrows():
                        record = {
                            'material': row['id'],
                            'rank': row['rank'],
                            'metric': metric,
                            'mean_value': row[metric]
                        }
                        if fits.get(row['id']):
                            record.update({
                                'fit_slope_stderr': fits[row['id']]['slope_stderr'],
                                'fit_r_squared': fits[row['id']]['r_squared'],
                                'fit_rmse': fits[row['id']]['rmse']
                            })
                        materials.append(record)
                    
                    ranks_by_force[f"f{f}"] = materials

                if plot_config.get('filename'):
                    filename = plot_config['filename']
                else:
                    layer_str = f"_layer{layer}" if layer else ""
                    filename = f'friction_ranking_{metric}_{size}{layer_str}.json'
                
                output_path = os.path.join(self.output_dir, filename)
                with open(output_path, 'w') as f:
                    json.dump(ranks_by_force, f, indent=4)
                log.info(f"Exported ranking to {output_path}")

    # =========================================================================
    # MAIN DISPATCHER
    # =========================================================================

    def generate_plot(self, plot_config):
        """Dispatches to the appropriate plot generation method."""
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
            log.error(f"Unknown plot type '{plot_type}'")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Generate plots from simulation data.")
    parser.add_argument('plot_config', help="Path to the JSON plot configuration file.")
    parser.add_argument('--output_dir', default='plots', help="Directory to save plots.")
    parser.add_argument('--settings', help="Path to plot settings JSON file.")
    parser.add_argument('--verbose', action='store_true', help="Enable verbose output.")
    parser.add_argument('--quiet', action='store_true', help="Suppress non-error output.")
    args = parser.parse_args()

    # Set logging level
    global log
    if args.quiet:
        log = Logger(Logger.QUIET)
    elif args.verbose:
        log = Logger(Logger.VERBOSE)
    else:
        log = Logger(Logger.NORMAL)

    # Load plot configuration
    try:
        with open(args.plot_config, 'r') as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log.error(f"Loading config file {args.plot_config}: {e}")
        return

    # Load settings if provided
    settings = None
    if args.settings:
        try:
            with open(args.settings, 'r') as f:
                settings = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            log.warning(f"Loading settings file {args.settings}: {e}. Using defaults.")

    data_dirs = config.get('data_dirs', [])
    labels = config.get('labels', [])
    plots = config.get('plots', [])

    if not data_dirs or not labels or not plots:
        log.error("'data_dirs', 'labels', and 'plots' must be defined in config.")
        return
    
    if len(data_dirs) != len(labels):
        log.error("Number of 'data_dirs' must match number of 'labels'.")
        return

    plotter = Plotter(data_dirs, labels, args.output_dir, settings)
    
    for plot_config in plots:
        plotter.generate_plot(plot_config)


if __name__ == '__main__':
    main()