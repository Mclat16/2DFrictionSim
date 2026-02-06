"""Standalone AiiDA integration module.

This module provides functions to register simulations with AiiDA without
modifying core builder or simulation_base files. It scans generated simulation
directories and creates provenance/simulation nodes as needed.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional

from src.aiida import AIIDA_AVAILABLE

if not AIIDA_AVAILABLE:
    raise ImportError("AiiDA is not installed. Install with: "
                     "conda install -c conda-forge aiida-core")

from src.aiida.data import (
    FrictionProvenanceData,
    FrictionSimulationData,
    FrictionResultsData
)

logger = logging.getLogger(__name__)


def register_simulation_batch(simulation_dirs: List[Path], config_path: Path) -> List[str]:
    """Register a batch of simulations with AiiDA.
    
    Scans each simulation directory for provenance folder and creates
    appropriate AiiDA nodes.
    
    Args:
        simulation_dirs: List of simulation output directories
        config_path: Path to original config file
        
    Returns:
        List of created simulation node UUIDs
    """
    created_uuids = []
    
    for sim_dir in simulation_dirs:
        try:
            uuid = register_single_simulation(sim_dir, config_path)
            if uuid:
                created_uuids.append(uuid)
        except Exception as e:
            logger.warning("Failed to register %s: %s", sim_dir, e)
            continue
    
    return created_uuids


def register_single_simulation(sim_dir: Path, config_path: Path) -> Optional[str]:
    """Register a single simulation with AiiDA.
    
    Args:
        sim_dir: Simulation output directory
        config_path: Path to original config file
        
    Returns:
        UUID of created simulation node, or None if failed
    """
    prov_dir = sim_dir / 'provenance'
    
    if not prov_dir.exists():
        logger.warning("No provenance folder found in %s", sim_dir)
        return None
    
    prov_node = create_provenance_node(prov_dir, config_path)
    
    config_file = prov_dir / 'config.json'
    if not config_file.exists():
        logger.warning("No config.json in provenance folder")
        return None
    
    config_data = json.loads(config_file.read_text())
    
    sim_node = FrictionSimulationData()
    
    sim_node.simulation_type = 'afm' if 'tip' in config_data else 'sheetonsheet'
    sim_node.material = config_data.get('2D', {}).get('mat', 'unknown')
    
    if 'general' in config_data:
        sim_node.temperature = config_data['general'].get('temp', 300.0)
    
    if 'sheet' in config_data and 'layers' in config_data['sheet']:
        layers = config_data['sheet']['layers']
        sim_node.layers = layers if isinstance(layers, int) else layers[0]
    
    sim_node.simulation_path = str(sim_dir.relative_to(sim_dir.parent.parent))
    sim_node.status = 'prepared'
    
    if prov_node:
        sim_node.base.attributes.set('provenance_uuid', str(prov_node.uuid))
    
    sim_node.store()
    
    manifest_path = prov_dir / 'manifest.json'
    if manifest_path.exists():
        manifest_data = json.loads(manifest_path.read_text())
        manifest_data['simulation_node_uuid'] = str(sim_node.uuid)
        if prov_node:
            manifest_data['provenance_node_uuid'] = str(prov_node.uuid)
        manifest_path.write_text(json.dumps(manifest_data, indent=2))
    
    logger.info("Registered simulation: %s (UUID: %s)", sim_dir.name, sim_node.uuid)
    
    return str(sim_node.uuid)


def create_provenance_node(prov_dir: Path, config_path: Path) -> Optional[FrictionProvenanceData]:
    """Create provenance node from provenance directory.
    
    Args:
        prov_dir: Provenance directory containing CIFs, potentials, config
        config_path: Original config file path
        
    Returns:
        Created provenance node or None if failed
    """
    try:
        prov_node = FrictionProvenanceData()
        
        config_file = prov_dir / 'config.json'
        if config_file.exists():
            prov_node.base.repository.put_object_from_file(
                str(config_file), 'config.json'
            )
        
        manifest_file = prov_dir / 'manifest.json'
        if manifest_file.exists():
            manifest_data = json.loads(manifest_file.read_text())
            prov_node.base.attributes.set('file_manifest', manifest_data)
        
        cif_dir = prov_dir / 'cif'
        if cif_dir.exists():
            cif_files = {}
            for cif_file in cif_dir.glob('*.cif'):
                prov_node.base.repository.put_object_from_file(
                    str(cif_file), f'cif/{cif_file.name}'
                )
                cif_files[cif_file.name] = _compute_checksum(cif_file)
            prov_node.base.attributes.set('cif_files', cif_files)
        
        pot_dir = prov_dir / 'potentials'
        if pot_dir.exists():
            pot_files = {}
            for pot_file in pot_dir.iterdir():
                if pot_file.is_file():
                    prov_node.base.repository.put_object_from_file(
                        str(pot_file), f'potentials/{pot_file.name}'
                    )
                    pot_files[pot_file.name] = _compute_checksum(pot_file)
            prov_node.base.attributes.set('potential_files', pot_files)
        
        prov_node.base.attributes.set('config_filename', config_path.name)
        
        prov_node.store()
        logger.info("Created provenance node: %s", prov_node.uuid)
        
        return prov_node
        
    except Exception as e:
        logger.error("Failed to create provenance node: %s", e)
        return None


def import_results_to_aiida(results_dir: Path) -> List[str]:
    """Import completed simulation results into AiiDA.
    
    Reads results using DataReader (which calculates COF and lateral force),
    then stores in AiiDA with automatic summary statistics calculation.
    
    Args:
        results_dir: Directory containing simulation results
        
    Returns:
        List of created results node UUIDs
    """
    from src.postprocessing.read_data import DataReader
    
    reader = DataReader(results_dir=str(results_dir))
    
    created_uuids = []
    
    # The data structure from DataReader is nested:
    # material -> size -> substrate -> tip -> radius -> layer -> speed -> force/pressure -> angle -> DataFrame
    for material, size_data in reader.full_data_nested.items():
        for size_key, substrate_data in size_data.items():
            for _substrate, tip_data in substrate_data.items():
                for _tip_mat, radius_data in tip_data.items():
                    for _radius, layer_data in radius_data.items():
                        for layer_key, speed_data in layer_data.items():
                            layers = int(layer_key.replace('l', ''))
                            
                            for speed_key, force_data in speed_data.items():
                                speed = int(speed_key.replace('s', ''))
                                
                                for load_key, angle_data in force_data.items():
                                    # Parse force or pressure
                                    is_pressure = load_key.startswith('p')
                                    load_val = float(load_key[1:])
                                    
                                    for angle_key, df in angle_data.items():
                                        angle = int(angle_key.replace('a', ''))
                                        
                                        try:
                                            results_node = FrictionResultsData()
                                            
                                            # Set metadata
                                            results_node.material = material.replace('_', '-')
                                            results_node.layers = layers
                                            results_node.speed = speed
                                            results_node.angle = angle
                                            results_node.size = size_key
                                            
                                            if is_pressure:
                                                results_node.base.attributes.set('pressure', load_val)
                                            else:
                                                results_node.force = load_val
                                            
                                            # Convert DataFrame to time-series dict
                                            # DataReader already calculated COF and lateral_force
                                            time_series = {col: df[col].tolist() for col in df.columns}
                                            
                                            # Add time array from reader
                                            if reader.time_series:
                                                time_series['time'] = reader.time_series
                                            
                                            # Store time series (this auto-calculates summary stats)
                                            results_node.time_series = time_series
                                            results_node.is_complete = True
                                            
                                            results_node.store()
                                            created_uuids.append(str(results_node.uuid))
                                            
                                            logger.info("Imported: %s L%d %s%.1f A%d - COF: %.4f",
                                                       material, layers, 
                                                       'P' if is_pressure else 'F',
                                                       load_val, angle,
                                                       results_node.mean_cof)
                                            
                                        except Exception as e:
                                            logger.warning("Failed to import %s/%s/%s: %s",
                                                         material, layer_key, load_key, e)
                                            continue
    
    return created_uuids


def _compute_checksum(file_path: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    import hashlib
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            sha256.update(chunk)
    return sha256.hexdigest()
