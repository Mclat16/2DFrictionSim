"""FrictionResultsData - Stores simulation results (time-series data).

This node stores the processed simulation results in a queryable format,
including full time-series data for detailed analysis.
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from aiida.orm import Data
import numpy as np


class FrictionResultsData(Data):
    """AiiDA Data node storing friction simulation results.
    
    Stores:
        - Time-series data (nf, lfx, lfy, lateral_force, cof, positions, etc.)
        - Summary statistics (mean, std for all fields)
        - Metadata about the results (ntimesteps, fields)
    
    Time-series data is stored as lists in attributes for PostgreSQL compatibility.
    Summary statistics are stored as direct attributes for efficient querying.
    """
    
    STANDARD_FIELDS = ['time', 'nf', 'lfx', 'lfy', 'lateral_force', 'cof',
                       'comx', 'comy', 'comz', 'tipx', 'tipy', 'tipz']
    
    def __init__(self, **kwargs):
        """Initialize the results data node."""
        super().__init__(**kwargs)
    
    # -------------------------------------------------------------------------
    # Time Series Data Storage
    # -------------------------------------------------------------------------
    
    @property
    def time_series(self) -> Dict[str, List[float]]:
        """The full time-series data as a dictionary of lists.
        
        Keys are field names (nf, lfx, lfy, etc.)
        Values are lists of floats for each timestep.
        """
        return self.base.attributes.get('time_series', {})
    
    @time_series.setter
    def time_series(self, value: Dict[str, List[float]]):
        # Ensure all values are lists (not numpy arrays) for storage
        serializable = {}
        for key, val in value.items():
            if hasattr(val, 'tolist'):
                serializable[key] = val.tolist()
            else:
                serializable[key] = list(val)
        self.base.attributes.set('time_series', serializable)
        
        # Auto-update metadata
        if serializable:
            lengths = [len(v) for v in serializable.values()]
            if lengths:
                self.ntimesteps = lengths[0]
                self.fields = list(serializable.keys())
        
        # Auto-calculate summary statistics
        self._calculate_summary_statistics()
    
    @property
    def time(self) -> List[float]:
        """Time values for the time series."""
        return self.time_series.get('time', [])
    
    @property
    def ntimesteps(self) -> int:
        """Number of timesteps in the data."""
        return self.base.attributes.get('ntimesteps', 0)
    
    @ntimesteps.setter
    def ntimesteps(self, value: int):
        self.base.attributes.set('ntimesteps', int(value))
    
    @property
    def fields(self) -> List[str]:
        """List of field names present in the data."""
        return self.base.attributes.get('fields', [])
    
    @fields.setter
    def fields(self, value: List[str]):
        self.base.attributes.set('fields', list(value))
    
    # -------------------------------------------------------------------------
    # Simulation Identification (for linking back)
    # -------------------------------------------------------------------------
    
    @property
    def material(self) -> str:
        """Material this result is for."""
        return self.base.attributes.get('material', '')
    
    @material.setter
    def material(self, value: str):
        self.base.attributes.set('material', value)
    
    @property
    def layers(self) -> int:
        """Number of layers."""
        return self.base.attributes.get('layers', 1)
    
    @layers.setter
    def layers(self, value: int):
        self.base.attributes.set('layers', int(value))
    
    @property
    def force(self) -> float:
        """Applied force in nN."""
        return self.base.attributes.get('force', 0.0)
    
    @force.setter
    def force(self, value: float):
        self.base.attributes.set('force', float(value))
    
    @property
    def angle(self) -> float:
        """Scan angle in degrees."""
        return self.base.attributes.get('angle', 0.0)
    
    @angle.setter
    def angle(self, value: float):
        self.base.attributes.set('angle', float(value))
    
    @property
    def speed(self) -> float:
        """Scan speed in m/s."""
        return self.base.attributes.get('speed', 2.0)
    
    @speed.setter
    def speed(self, value: float):
        self.base.attributes.set('speed', float(value))
    
    @property
    def size(self) -> str:
        """Size identifier (e.g., '100x100')."""
        return self.base.attributes.get('size', '')
    
    @size.setter
    def size(self, value: str):
        self.base.attributes.set('size', value)
    
    @property
    def is_complete(self) -> bool:
        """Whether this result represents a complete simulation."""
        return self.base.attributes.get('is_complete', True)
    
    @is_complete.setter
    def is_complete(self, value: bool):
        self.base.attributes.set('is_complete', bool(value))
    
    # -------------------------------------------------------------------------
    # Summary Statistics Properties
    # -------------------------------------------------------------------------
    
    @property
    def mean_nf(self) -> float:
        """Mean normal force."""
        return self.base.attributes.get('mean_nf', 0.0)
    
    @property
    def mean_lfx(self) -> float:
        """Mean lateral force (x-direction)."""
        return self.base.attributes.get('mean_lfx', 0.0)
    
    @property
    def mean_lfy(self) -> float:
        """Mean lateral force (y-direction)."""
        return self.base.attributes.get('mean_lfy', 0.0)
    
    @property
    def mean_lateral_force(self) -> float:
        """Mean magnitude of lateral force."""
        return self.base.attributes.get('mean_lateral_force', 0.0)
    
    @property
    def mean_cof(self) -> float:
        """Mean coefficient of friction."""
        return self.base.attributes.get('mean_cof', 0.0)
    
    @property
    def std_cof(self) -> float:
        """Standard deviation of coefficient of friction."""
        return self.base.attributes.get('std_cof', 0.0)
    
    @property
    def friction_coefficient(self) -> float:
        """Friction coefficient (alias for mean_cof)."""
        return self.mean_cof
    
    def _calculate_summary_statistics(self):
        """Calculate and store summary statistics from time-series data."""
        ts = self.time_series
        
        if not ts:
            return
        
        # Calculate statistics for each field
        for field in ['nf', 'lfx', 'lfy', 'lateral_force', 'cof']:
            if field in ts:
                arr = np.array(ts[field])
                self.base.attributes.set(f'mean_{field}', float(np.mean(arr)))
                self.base.attributes.set(f'std_{field}', float(np.std(arr)))
                self.base.attributes.set(f'min_{field}', float(np.min(arr)))
                self.base.attributes.set(f'max_{field}', float(np.max(arr)))
        
        # Set friction_coefficient as alias for mean_cof
        if 'cof' in ts:
            self.base.attributes.set('friction_coefficient', self.mean_cof)
    
    def get_summary_statistics(self) -> Dict[str, Dict[str, float]]:
        """Get all summary statistics as a nested dictionary.
        
        Returns:
            Dictionary with structure: {field: {stat_name: value}}
        """
        summary = {}
        for field in ['nf', 'lfx', 'lfy', 'lateral_force', 'cof']:
            field_stats = {}
            for stat in ['mean', 'std', 'min', 'max']:
                key = f'{stat}_{field}'
                val = self.base.attributes.get(key)
                if val is not None:
                    field_stats[stat] = val
            if field_stats:
                summary[field] = field_stats
        
        summary['friction_coefficient'] = self.friction_coefficient
        return summary
    
    # -------------------------------------------------------------------------
    # Data Access Methods (return numpy arrays for analysis)
    # -------------------------------------------------------------------------
    
    def get_array(self, field: str) -> np.ndarray:
        """Get a field as a numpy array.
        
        Args:
            field: Field name (e.g., 'nf', 'lfx', 'lfy')
            
        Returns:
            Numpy array of values
            
        Raises:
            KeyError: If field not found
        """
        if field not in self.time_series:
            raise KeyError(f"Field '{field}' not found. Available: {self.fields}")
        return np.array(self.time_series[field])
    
    def get_normal_force(self) -> np.ndarray:
        """Get normal force time series."""
        return self.get_array('nf')
    
    def get_lateral_force_x(self) -> np.ndarray:
        """Get lateral force (x-direction) time series."""
        return self.get_array('lfx')
    
    def get_lateral_force_y(self) -> np.ndarray:
        """Get lateral force (y-direction) time series."""
        return self.get_array('lfy')
    
    def get_lateral_force_magnitude(self) -> np.ndarray:
        """Get magnitude of lateral force."""
        lfx = self.get_lateral_force_x()
        lfy = self.get_lateral_force_y()
        return np.sqrt(lfx**2 + lfy**2)
    
    # -------------------------------------------------------------------------
    # Statistical Methods
    # -------------------------------------------------------------------------
    
    def compute_mean(self, field: str, skip_fraction: float = 0.2) -> float:
        """Compute mean of a field, optionally skipping initial transient.
        
        Args:
            field: Field name
            skip_fraction: Fraction of initial data to skip (default 20%)
            
        Returns:
            Mean value
        """
        data = self.get_array(field)
        skip_n = int(len(data) * skip_fraction)
        return float(np.mean(data[skip_n:]))
    
    def compute_std(self, field: str, skip_fraction: float = 0.2) -> float:
        """Compute standard deviation of a field.
        
        Args:
            field: Field name
            skip_fraction: Fraction of initial data to skip (default 20%)
            
        Returns:
            Standard deviation
        """
        data = self.get_array(field)
        skip_n = int(len(data) * skip_fraction)
        return float(np.std(data[skip_n:]))
    
    def get_friction_coefficient(self, skip_fraction: float = 0.2) -> float:
        """Calculate friction coefficient (mu = Fl / Fn).
        
        Args:
            skip_fraction: Fraction of initial data to skip
            
        Returns:
            Mean friction coefficient
        """
        nf = self.get_array('nf')
        lf = self.get_lateral_force_magnitude()
        skip_n = int(len(nf) * skip_fraction)
        
        # Avoid division by zero
        nf_slice = nf[skip_n:]
        lf_slice = lf[skip_n:]
        
        # Calculate instantaneous friction coefficient
        with np.errstate(divide='ignore', invalid='ignore'):
            mu = np.where(nf_slice > 0, lf_slice / nf_slice, 0)
        
        return float(np.mean(mu))
    
    def get_summary_statistics(self, skip_fraction: float = 0.2) -> Dict[str, Any]:
        """Get summary statistics for all fields.
        
        Args:
            skip_fraction: Fraction of initial data to skip
            
        Returns:
            Dictionary with mean and std for each field
        """
        stats = {}
        for field in self.fields:
            if field == 'time':
                continue
            try:
                stats[field] = {
                    'mean': self.compute_mean(field, skip_fraction),
                    'std': self.compute_std(field, skip_fraction)
                }
            except Exception:
                pass
        
        # Add friction coefficient
        try:
            stats['friction_coefficient'] = self.get_friction_coefficient(skip_fraction)
        except Exception:
            pass
        
        return stats
    
    # -------------------------------------------------------------------------
    # Factory Methods
    # -------------------------------------------------------------------------
    
    @classmethod
    def from_dataframe(cls, df, metadata: Dict[str, Any] = None) -> 'FrictionResultsData':
        """Create from a pandas DataFrame.
        
        Args:
            df: DataFrame with columns for each field
            metadata: Optional metadata dict (material, layers, force, angle, speed)
            
        Returns:
            New FrictionResultsData instance
        """
        node = cls()
        
        # Convert DataFrame to dict of lists
        time_series = {}
        for col in df.columns:
            time_series[col] = df[col].tolist()
        
        node.time_series = time_series
        node.fields = list(df.columns)
        node.ntimesteps = len(df)
        
        # Set metadata if provided
        if metadata:
            if 'material' in metadata:
                node.material = metadata['material']
            if 'layers' in metadata:
                node.layers = metadata['layers']
            if 'force' in metadata:
                node.force = metadata['force']
            if 'angle' in metadata:
                node.angle = metadata['angle']
            if 'speed' in metadata:
                node.speed = metadata['speed']
            if 'size' in metadata:
                node.size = metadata['size']
        
        return node
    
    @classmethod
    def from_json(cls, json_data: Union[str, Dict]) -> 'FrictionResultsData':
        """Create from JSON data (as exported by read_data.py).
        
        Args:
            json_data: JSON string or parsed dict
            
        Returns:
            New FrictionResultsData instance
        """
        if isinstance(json_data, str):
            data = json.loads(json_data)
        else:
            data = json_data
        
        node = cls()
        
        if 'metadata' in data:
            meta = data['metadata']
            if 'time_series' in meta:
                node.time_series = {'time': meta['time_series']}
        
        # Handle the nested results structure from read_data.py
        # This will need to be adapted based on actual JSON structure
        
        return node
    
    def to_dict(self) -> Dict[str, Any]:
        """Export all data as a dictionary."""
        return {
            'uuid': str(self.uuid),
            'material': self.material,
            'layers': self.layers,
            'force': self.force,
            'angle': self.angle,
            'speed': self.speed,
            'size': self.size,
            'ntimesteps': self.ntimesteps,
            'fields': self.fields,
            'is_complete': self.is_complete,
            'time_series': self.time_series,
        }
    
    def __repr__(self) -> str:
        return (
            f"<FrictionResultsData: {self.material} "
            f"L{self.layers} F{self.force}nN A{self.angle}° "
            f"({self.ntimesteps} steps)>"
        )
