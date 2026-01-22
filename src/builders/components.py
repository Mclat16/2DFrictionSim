"""Component builders for FrictionSim2D.

This module contains the logic to construct the physical components of the simulation:
the AFM tip, the substrate, and the 2D material sheet. It handles the calculation
of duplication factors based on requested dimensions and unit cell properties.

Function Organization:
1. Low-level utilities (run_lammps_commands, calculate_layer_shifts)
2. Slab creation (create_orthogonal_slab)
3. Amorphous material helpers (get_amorphous_path, make_amorphous)
4. Sheet stacking helpers (stack_multilayer_sheet)
5. Main builders (build_tip, build_substrate, build_sheet)
"""

import logging
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple, cast
from importlib import resources
import subprocess
import numpy as np

from ase import io as ase_io
from jinja2 import Environment
from lammps import lammps

from src.core.config import GlobalSettings, SheetConfig, SubstrateConfig, TipConfig, ComponentConfig
from src.core.potential_manager import PotentialManager
from src.core.utils import (
    cifread, count_atomtypes, get_material_path, get_model_dimensions,
    renumber_atom_types, check_potential_cif_compatibility
)
from src.interfaces.atomsk import AtomskWrapper
from src.interfaces.jinja import PackageLoader
from src.interfaces.lammps import run_lammps_commands

logger = logging.getLogger(__name__)

def calculate_layer_shifts(mat_name: str, dims: Dict[str, float]) -> Tuple[float, float]:
    """Calculate in-plane stacking shifts based on material type.
    
    Args:
        mat_name: Material name.
        dims: Box dimensions with xlo, xhi, ylo, yhi keys.
        
    Returns:
        Tuple of (shift_x, shift_y) for layer stacking.
    """
    if mat_name.startswith('p-') or mat_name == 'black_phosphorus':
        return (dims['xhi'] - dims['xlo']) / 2, (dims['yhi'] - dims['ylo']) / 2
    return 0, (dims['yhi'] - dims['ylo']) / 3

def create_orthogonal_slab(
    cif_path: Path,
    output_path: Path,
    target_x: float,
    target_y: float,
    target_z: Optional[float] = None,
    atomsk: Optional[AtomskWrapper] = None
) -> Tuple[Path, Dict[str, float], List[int]]:
    """Create orthogonalized slab from CIF file sized to target dimensions.
    
    Args:
        cif_path: Input CIF file path.
        output_path: Output LAMMPS data file path.
        target_x: Target X dimension (Angstroms).
        target_y: Target Y dimension (Angstroms).
        target_z: Target Z dimension (Angstroms), or None for single layer.
        atomsk: AtomskWrapper instance (created if not provided).
        
    Returns:
        Tuple of (output_path, box_dimensions, duplication_factors).
    """
    atomsk = atomsk or AtomskWrapper()
    cif_path = Path(cif_path).absolute()

    ortho_cell = Path(tempfile.gettempdir()) / f"{cif_path.stem}_{uuid.uuid4().hex[:8]}_ortho.lmp"
    atomsk.create_slab(cif_path, ortho_cell, pre_duplicate=[2, 2, 1])

    dims = get_model_dimensions(ortho_cell)
    assert all(dims[k] is not None for k in ['xhi', 'xlo', 'yhi', 'ylo', 'zhi', 'zlo'])

    unit_x = (cast(float, dims['xhi']) - cast(float, dims['xlo'])) / 2.0
    unit_y = (cast(float, dims['yhi']) - cast(float, dims['ylo'])) / 2.0
    unit_z = cast(float, dims['zhi']) - cast(float, dims['zlo'])

    dup_x = max(1, round(target_x / unit_x / 2.0))
    dup_y = max(1, round(target_y / unit_y / 2.0))
    dup_z = 1 if target_z is None else max(1, round(target_z / unit_z))

    duplication = [dup_x, dup_y, dup_z]

    if dup_x == 1 and dup_y == 1 and dup_z == 1:
        shutil.copy(ortho_cell, output_path)
    else:
        atomsk.duplicate(ortho_cell, output_path, dup_x, dup_y, dup_z)

    ortho_cell.unlink()

    final_dims = get_model_dimensions(output_path)
    assert all(final_dims[k] is not None for k in ['xhi', 'xlo', 'yhi', 'ylo', 'zhi', 'zlo'])
    final_dims_typed: Dict[str, float] = {k: cast(float, v) for k, v in final_dims.items()}
    return output_path, final_dims_typed, duplication

def get_amorphous_path(mat_name: str) -> Optional[Path]:
    """Get path to pre-generated amorphous material file if it exists.
    
    Args:
        mat_name: Material name.
        
    Returns:
        Path to amorphous file or None.
    """
    mat_dir = resources.files('src.data.materials')
    amor_file = mat_dir.joinpath(f"amor_{mat_name}.lmp")
    return Path(str(amor_file)) if amor_file.is_file() else None

def make_amorphous(
    mat_name: str,
    cif_path: Path,
    target_x: float,
    target_y: float,
    target_z: float,
    pot_path: Path,
    pot_type: str,
    output_dir: Path,
    settings: GlobalSettings
) -> Path:
    """Get or generate amorphous structure via melt-quench procedure.
    
    Args:
        mat_name: Material name.
        cif_path: Crystalline CIF file path.
        target_x: Required X dimension (Angstroms).
        target_y: Required Y dimension (Angstroms).
        target_z: Required Z dimension (Angstroms).
        pot_path: Potential file path.
        pot_type: Potential type (sw, tersoff, etc.).
        output_dir: Directory for temporary files.
        settings: Global settings with quench parameters.
        
    Returns:
        Path to amorphous structure file with sufficient dimensions.
    """
    amor_path = get_amorphous_path(mat_name)
    if amor_path:
        amor_dims = get_model_dimensions(amor_path)
        assert all(amor_dims[k] is not None for k in ['xhi', 'xlo', 'yhi', 'ylo', 'zhi', 'zlo'])

        amor_x = cast(float, amor_dims['xhi']) - cast(float, amor_dims['xlo'])
        amor_y = cast(float, amor_dims['yhi']) - cast(float, amor_dims['ylo'])
        amor_z = cast(float, amor_dims['zhi']) - cast(float, amor_dims['zlo'])

        if amor_x >= target_x and amor_y >= target_y and amor_z >= target_z:
            logger.info("Using existing amorphous file: %s", amor_path)
            return amor_path
        logger.info(
            "Existing amorphous file too small (%.1fx%.1fx%.1f vs %.1fx%.1fx%.1f), regenerating...",
            amor_x, amor_y, amor_z, target_x, target_y, target_z
        )

    logger.info("Generating amorphous %s via melt-quench...", mat_name)

    quench = settings.quench
    slab_x = max(quench.quench_slab_dims[0], target_x)
    slab_y = max(quench.quench_slab_dims[1], target_y)
    slab_z = max(quench.quench_slab_dims[2], target_z)

    if (slab_x > quench.quench_slab_dims[0] or
        slab_y > quench.quench_slab_dims[1] or
        slab_z > quench.quench_slab_dims[2]):
        logger.info(
            "Increasing slab dimensions from (%dx%dx%d) to required (%.1fx%.1fx%.1f)",
            quench.quench_slab_dims[0], quench.quench_slab_dims[1],
            quench.quench_slab_dims[2], slab_x, slab_y, slab_z
        )

    atomsk = AtomskWrapper()
    base_block = output_dir / f"{mat_name}_crystal_block.lmp"
    create_orthogonal_slab(
        cif_path, base_block,
        target_x=slab_x, target_y=slab_y, target_z=slab_z,
        atomsk=atomsk
    )

    mat_dir = resources.files('src.data.materials')
    materials_path = Path(str(mat_dir))
    materials_path.mkdir(parents=True, exist_ok=True)

    amor_file = materials_path / f"amor_{mat_name}.lmp"

    cif_data = cifread(cif_path)
    elements = cif_data['elements']

    temp_config = ComponentConfig(
        mat=mat_name,
        pot_type=pot_type,
        pot_path=str(pot_path),
        cif_path=str(cif_path)
    )

    pm = PotentialManager(settings, use_langevin=False)
    pot_commands = pm.get_single_component_commands(temp_config, elements)

    quench_rate = float(quench.quench_rate) * 1e-12 / float(quench.timestep)
    quench_nsteps = max(int((quench.melt_temp - quench.quench_temp) * quench_rate), 1)

    lmp_input_path = output_dir / f"lmp_input_amorphous_{mat_name}.in"

    jinja_env = Environment(
        loader=PackageLoader('src.templates'),
        trim_blocks=True,
        lstrip_blocks=True
    )

    context = {
        'neighbor_list': settings.simulation.neighbor_list,
        'neigh_modify_command': settings.simulation.neigh_modify_command,
        'base_block': base_block,
        'pot_commands': pot_commands,
        'min_style': settings.simulation.min_style,
        'minimization_command': settings.simulation.minimization_command,
        'timestep': quench.timestep,
        'melt_temp': quench.melt_temp,
        'melt_steps': quench.melt_steps,
        'quench_temp': quench.quench_temp,
        'quench_nsteps': quench_nsteps,
        'equilibrate_steps': quench.equilibrate_steps,
        'amor_file': amor_file
    }

    template = jinja_env.get_template('common/make_amorphous.lmp')
    script_content = template.render(context)
    lmp_input_path.write_text(script_content, encoding='utf-8')

    if quench.run_local:
        logger.info("Running melt-quench with %d processors...", quench.n_procs)
        try:
            subprocess.run(
                f"mpiexec -np {quench.n_procs} lmp -in {lmp_input_path}",
                shell=True, check=True
            )
        except subprocess.CalledProcessError as e:
            logger.error("Melt-quench LAMMPS run failed: %s", e)
            raise
    else:
        local_lmp_input = output_dir / f"make_amorphous_{mat_name}.in"
        shutil.copy(lmp_input_path, local_lmp_input)
        logger.info(
            "LAMMPS input file for amorphous structure generation saved to: %s",
            local_lmp_input
        )
        logger.info("Please run the following command to generate the amorphous structure:")
        logger.info("mpiexec -np %d lmp -in %s", quench.n_procs,
                    local_lmp_input)
        logger.info("After the simulation is complete, please rerun the program.")
        raise RuntimeError(
            f"Amorphous structure generation requires manual LAMMPS run. "
            f"See {local_lmp_input} for input script."
        )

    if base_block.exists():
        base_block.unlink()
    if lmp_input_path.exists():
        lmp_input_path.unlink()

    logger.info("Created amorphous structure in materials folder: %s", amor_file)
    return amor_file

def _create_base_slab(
    config,
    cif_path: Path,
    target_x: float,
    target_y: float,
    target_z: float,
    output_path: Path,
    build_dir: Path,
    settings: GlobalSettings,
    atomsk: AtomskWrapper
) -> None:
    """Create base slab (amorphous or crystalline).
    
    Args:
        config: TipConfig or SubstrateConfig.
        cif_path: CIF file path.
        target_x: Target X dimension (Angstroms).
        target_y: Target Y dimension (Angstroms).
        target_z: Target Z dimension (Angstroms).
        output_path: Output slab file path.
        build_dir: Directory for temporary files.
        settings: Global simulation settings.
        atomsk: AtomskWrapper instance.
    """
    if config.amorph == 'a':
        pot_path = get_material_path(config.pot_path, config.pot_type)
        amor_path = make_amorphous(
            config.mat, cif_path,
            target_x=target_x, target_y=target_y, target_z=target_z,
            pot_path=pot_path, pot_type=config.pot_type,
            output_dir=build_dir, settings=settings
        )
        shutil.copy(amor_path, output_path)
    else:
        create_orthogonal_slab(
            cif_path, output_path,
            target_x=target_x, target_y=target_y, target_z=target_z,
            atomsk=atomsk
        )


def stack_multilayer_sheet(
    base_layer_path: Path,
    config: SheetConfig,
    output_path: Path,
    box_dims: Dict[str, float],
    n_layers: int,
    types_per_layer: int,
    pot_counts: Dict[str, int],
    lat_c: Optional[float] = None,
    settings: Optional[GlobalSettings] = None
) -> Tuple[Path, float]:
    """Stack multiple 2D material layers with proper atom type renumbering.
    
    Args:
        base_layer_path: Single-layer LAMMPS data file path.
        config: Sheet configuration.
        output_path: Stacked output file path.
        box_dims: Box dimensions from base layer.
        n_layers: Number of layers to stack.
        types_per_layer: Atom types per layer before renumbering.
        pot_counts: Element to type count mapping.
        lat_c: Interlayer distance (calculated if None).
        settings: Global settings (required if lat_c is None).
        
    Returns:
        Tuple of (output_path, lat_c).
    """
    if n_layers < 2:
        raise ValueError("stack_multilayer_sheet requires at least 2 layers")

    sx, sy = calculate_layer_shifts(config.mat, box_dims)
    calculate_lat_c = lat_c is None

    if calculate_lat_c:
        assert settings is not None, "settings required for lat_c calculation"
        logger.info("Running minimization to find optimal interlayer distance")
        initial_guess = settings.geometry.lat_c_default
    else:
        assert settings is not None
        initial_guess = lat_c

    pot_file = Path(tempfile.gettempdir()) / f"sheet_{n_layers}_{uuid.uuid4().hex[:8]}.in.settings"
    layers_for_setup = 2 if calculate_lat_c else n_layers

    pm = PotentialManager(settings)
    pm.register_component("sheet", config, n_layers=layers_for_setup)
    pm.add_self_interaction("sheet")

    if pm.is_sheet_lj(config.pot_type):
        pm.add_interlayer_interaction("sheet")

    pm.write_file(pot_file)

    total_types = len(pm.types)
    max_z = initial_guess * (layers_for_setup - 1) + 20.0

    jinja_env = Environment(
        loader=PackageLoader('src.templates'),
        trim_blocks=True,
        lstrip_blocks=True
    )

    layer_shifts = [initial_guess * l for l in range(layers_for_setup)]

    context = {
        'box_xlo': box_dims['xlo'],
        'box_xhi': box_dims['xhi'],
        'box_ylo': box_dims['ylo'],
        'box_yhi': box_dims['yhi'],
        'box_zhi': max_z,
        'total_types': total_types,
        'base_layer_path': base_layer_path,
        'n_layers': layers_for_setup,
        'layer_shifts': layer_shifts,
        'shift_x': sx,
        'shift_y': sy,
        'types_per_layer': types_per_layer,
        'pot_counts': pot_counts,
        'pot_file': pot_file,
        'calculate_lat_c': calculate_lat_c,
        'min_style': settings.simulation.min_style if calculate_lat_c else None,
        'minimization_command': settings.simulation.minimization_command if calculate_lat_c else None,
        'timestep': settings.simulation.timestep if calculate_lat_c else None,
        'output_path': output_path
    }

    template = jinja_env.get_template('common/stack_layers.lmp')
    commands = template.render(context).strip().split('\n')
    commands = [cmd.strip() for cmd in commands if cmd.strip() and not cmd.strip().startswith('#')]

    lmp = lammps(cmdargs=["-log", "none", "-screen", "none", "-nocite"])
    try:
        for cmd in commands:
            lmp.command(cmd)

        if calculate_lat_c:
            extracted = lmp.extract_variable("lat_c", None, 0)
            lat_c = float(extracted) if extracted is not None else initial_guess
            logger.info("Found optimal lat_c: %.4f", lat_c)

            if n_layers > 2:
                lmp.close()
                return stack_multilayer_sheet(
                    base_layer_path=base_layer_path,
                    config=config,
                    output_path=output_path,
                    box_dims=box_dims,
                    n_layers=n_layers,
                    types_per_layer=types_per_layer,
                    pot_counts=pot_counts,
                    lat_c=lat_c,
                    settings=settings
                )

        lat_c = lat_c or initial_guess

    except Exception as e:
        logger.error("Failed to stack layers: %s", e)
        if calculate_lat_c:
            lat_c = settings.geometry.lat_c_default
        raise
    finally:
        lmp.close()
        if pot_file.exists():
            pot_file.unlink()

    return output_path, lat_c


def build_tip(
    config: TipConfig,
    atomsk: AtomskWrapper,
    build_dir: Path,
    settings: GlobalSettings
) -> Tuple[Path, float]:
    """Build AFM tip structure (spherical geometry).
    
    Args:
        config: Tip configuration.
        atomsk: AtomskWrapper instance.
        build_dir: Output directory.
        settings: Global simulation settings.
        
    Returns:
        Tuple of (tip_path, actual_radius).
    """
    cif_path = get_material_path(config.cif_path, 'cif')

    base_lmp = Path(tempfile.gettempdir()) / f"{config.mat}_{uuid.uuid4().hex[:8]}_base.lmp"
    final_lmp = build_dir / "tip.lmp"
    radius = config.r
    box_size = radius * 2.0

    _create_base_slab(
        config, cif_path,
        target_x=box_size, target_y=box_size, target_z=box_size,
        output_path=base_lmp, build_dir=build_dir,
        settings=settings, atomsk=atomsk
    )

    if config.amorph != 'a':
        dim = get_model_dimensions(base_lmp)
        assert all(dim[k] is not None for k in ['xhi', 'xlo', 'yhi', 'ylo'])
        radius = min(cast(float, dim['xhi']) - cast(float, dim['xlo']),
                    cast(float, dim['yhi']) - cast(float, dim['ylo'])) / 2.0

    h = radius / settings.geometry.tip_reduction_factor

    jinja_env = Environment(
        loader=PackageLoader('src.templates'),
        trim_blocks=True,
        lstrip_blocks=True
    )

    context = {
        'base_lmp': base_lmp,
        'radius': radius,
        'tip_height': h,
        'output_path': final_lmp
    }

    template = jinja_env.get_template('common/build_tip.lmp')
    commands = template.render(context).strip().split('\n')
    commands = [cmd.strip() for cmd in commands if cmd.strip() and not cmd.strip().startswith('#')]

    run_lammps_commands(commands)
    base_lmp.unlink()
    return final_lmp, radius

def build_substrate(
    config: SubstrateConfig,
    atomsk: AtomskWrapper,
    build_dir: Path,
    box_dims: dict,
    settings: Optional[GlobalSettings] = None
) -> Path:
    """Build substrate slab.
    
    Args:
        config: Substrate configuration.
        atomsk: AtomskWrapper instance.
        build_dir: Output directory.
        box_dims: Target box dimensions from sheet.
        settings: Global settings (required for amorphous).
        
    Returns:
        Path to substrate file.
    """
    if config.amorph == 'a':
        assert settings is not None, "settings required for amorphous substrate"

    cif_path = get_material_path(config.cif_path, 'cif')
    base_lmp = Path(tempfile.gettempdir()) / f"{config.mat}_{uuid.uuid4().hex[:8]}_base.lmp"
    final_lmp = build_dir / "sub.lmp"
    target_x = box_dims['xhi'] - box_dims['xlo']
    target_y = box_dims['yhi'] - box_dims['ylo']
    target_z = config.thickness

    _create_base_slab(
        config, cif_path,
        target_x=target_x, target_y=target_y, target_z=target_z,
        output_path=base_lmp, build_dir=build_dir,
        settings=settings or GlobalSettings(), atomsk=atomsk
    )

    jinja_env = Environment(
        loader=PackageLoader('src.templates'),
        trim_blocks=True,
        lstrip_blocks=True
    )

    context = {
        'base_lmp': base_lmp,
        'box_xlo': box_dims['xlo'],
        'box_xhi': box_dims['xhi'],
        'box_ylo': box_dims['ylo'],
        'box_yhi': box_dims['yhi'],
        'box_zlo': box_dims['zlo'],
        'target_z': target_z,
        'output_path': final_lmp
    }

    template = jinja_env.get_template('common/build_substrate.lmp')
    commands = template.render(context).strip().split('\n')
    commands = [cmd.strip() for cmd in commands if cmd.strip() and not cmd.strip().startswith('#')]

    run_lammps_commands(commands)
    base_lmp.unlink()
    return final_lmp

def build_monolayer(
    config: SheetConfig,
    atomsk: AtomskWrapper,
    build_dir: Path,
    settings: Optional[GlobalSettings] = None
) -> Tuple[Path, dict, float, dict, int]:
    """Build single-layer 2D material sheet.
    
    Args:
        config: Sheet configuration.
        atomsk: AtomskWrapper instance.
        build_dir: Output directory.
        settings: Global simulation settings.
        
    Returns:
        Tuple of (path, box_dims, lat_c, pot_counts, total_types).
    """
    cif_path = get_material_path(config.cif_path, 'cif')
    pot_path = get_material_path(config.pot_path, config.pot_type)
    base_path = build_dir / f"{config.mat}_1.lmp"

    cif_data = cifread(cif_path)
    pot_counts = count_atomtypes(pot_path, cif_data['elements'])
    total_pot_types = sum(pot_counts.values())

    multiplier = 1 if config.pot_type in ['rebo', 'rebomos', 'airebo', 'meam', 'reaxff'] else \
        check_potential_cif_compatibility(cif_path, pot_path)

    temp_unit_cell = Path(tempfile.gettempdir()) / f"{config.mat}_{uuid.uuid4().hex[:8]}_unit.lmp"
    atomsk.convert(cif_path, temp_unit_cell)

    if any(v != 1 for v in pot_counts.values()) or multiplier != 1:
        renumber_atom_types(temp_unit_cell)

    ortho_cell = Path(tempfile.gettempdir()) / f"{config.mat}_{uuid.uuid4().hex[:8]}_ortho.lmp"
    atomsk.orthogonalize(temp_unit_cell, ortho_cell)
    temp_unit_cell.unlink()

    dims = get_model_dimensions(ortho_cell)

    if multiplier != 1:
        atoms = ase_io.read(str(ortho_cell), format="lammps-data")
        natoms = len(atoms)
        a = 1
        b = 1
        if total_pot_types % natoms == 0:
            for i in range(int(np.sqrt(total_pot_types / natoms)) + 1, 0, -1):
                if (total_pot_types / natoms) % i == 0:
                    a = int(i)
                    b = int(total_pot_types / natoms / i)
                    break
            dup_ortho = Path(tempfile.gettempdir()) / f"{config.mat}_{uuid.uuid4().hex[:8]}_dup.lmp"
            atomsk.duplicate(ortho_cell, dup_ortho, a, b, 1)
            ortho_cell.unlink()
            ortho_cell = dup_ortho
            renumber_atom_types(ortho_cell, pot=list(pot_counts.keys()))
            dims = get_model_dimensions(ortho_cell)

    dims_calc = get_model_dimensions(ortho_cell)
    assert all(dims_calc[k] is not None for k in ['xhi', 'xlo', 'yhi', 'ylo'])

    unit_x = cast(float, dims_calc['xhi']) - cast(float, dims_calc['xlo'])
    unit_y = cast(float, dims_calc['yhi']) - cast(float, dims_calc['ylo'])

    target_x = config.x[0] if isinstance(config.x, list) else config.x
    target_y = config.y[0] if isinstance(config.y, list) else config.y
    dup_x = max(1, round(target_x / unit_x))
    dup_y = max(1, round(target_y / unit_y))

    if dup_x == 1 and dup_y == 1:
        shutil.copy(ortho_cell, base_path)
    else:
        atomsk.duplicate(ortho_cell, base_path, dup_x, dup_y, 1)
    ortho_cell.unlink()

    dims = get_model_dimensions(base_path)

    if config.pot_type in ['tersoff', 'sw', 'rebo', 'airebo']:
        atomsk.charge2atom(base_path)

    lat_c = config.lat_c or (settings.geometry.lat_c_default if settings else 6.0)

    return base_path, dims, lat_c, pot_counts, total_pot_types


def build_sheet(
    config: SheetConfig,
    atomsk: AtomskWrapper,
    build_dir: Path,
    stack_if_multi: bool = False,
    settings: Optional[GlobalSettings] = None,
    n_layers_override: Optional[int] = None
) -> Tuple[Path, dict, float]:
    """Build 2D material sheet (single or multi-layer).
    
    Args:
        config: Sheet configuration.
        atomsk: AtomskWrapper instance.
        build_dir: Output directory.
        stack_if_multi: If True, stack multiple layers.
        settings: Global settings (required for multi-layer).
        n_layers_override: Override layer count.
        
    Returns:
        Tuple of (path, box_dims, lat_c).
    """
    base_path, dims, lat_c, pot_counts, total_pot_types = build_monolayer(
        config, atomsk, build_dir, settings
    )

    n_layers = n_layers_override or (max(config.layers) if config.layers else 1)

    if stack_if_multi and n_layers > 1:
        assert settings is not None, "settings required for multi-layer stacking"
        stacked_path = build_dir / f"{config.mat}_{n_layers}.lmp"

        stacked_path, lat_c = stack_multilayer_sheet(
            base_layer_path=base_path,
            config=config,
            output_path=stacked_path,
            box_dims=dims,
            n_layers=n_layers,
            types_per_layer=total_pot_types,
            pot_counts=pot_counts,
            lat_c=lat_c,
            settings=settings
        )
        base_path.unlink()
        return stacked_path, dims, lat_c

    return base_path, dims, lat_c
