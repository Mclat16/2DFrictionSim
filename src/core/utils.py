"""A collection of utility functions for file processing and calculations.

This module provides tools for reading, writing, and modifying simulation
files (e.g., CIF, LAMMPS data), parsing configuration files, and calculating
physical parameters like Lennard-Jones coefficients.
"""
from importlib import resources
import configparser
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Union, Any, Optional
import math
from ase.io import read as ase_read

from src.data.potentials import UFF_params as lj

def get_material_path(mat_name: str, file_type: str = 'cif') -> Path:
    """Find material files in the package data.

    Args:
        mat_name: Material identifier or file path.
        file_type: File type extension (default 'cif').

    Returns:
        Path to the material file.
    """
    user_path = Path(mat_name)
    if user_path.exists():
        return user_path

    mat_dir = resources.files('src.data.materials')

    candidates = [
        mat_dir.joinpath(mat_name),
        mat_dir.joinpath(f"{mat_name}.{file_type}"),
        mat_dir.joinpath('cif').joinpath(mat_name),
        mat_dir.joinpath('cif').joinpath(f"{mat_name}.{file_type}"),
    ]

    for candidate in candidates:
        try:
            if candidate.is_file():
                return Path(str(candidate))
        except (TypeError, AttributeError):
            if isinstance(candidate, Path) and candidate.exists():
                return candidate

    return user_path

def get_potential_path(pot_name: str) -> Path:
    """Find potential files in the package data recursively.

    Handles cases where potentials are in subfolders like 'sw/', 'tersoff/'.

    Args:
        pot_name: Potential name or file path.

    Returns:
        Path to the potential file.
    """
    pot_dir = resources.files('src.data.potentials')

    direct_path = pot_dir.joinpath(pot_name)
    if direct_path.is_file():
        return Path(str(direct_path))

    target_name = Path(pot_name).name
    ext = Path(pot_name).suffix.lstrip('.')

    subdir_map = {
        'sw': 'sw',
        'tersoff': 'tersoff',
        'rebo': 'rebo',
        'airebo': 'airebo',
        'reaxff': 'reaxff',
        'meam': 'meam',
        'extep': 'extep',
        'vashishta': 'vashishta',
        'adp': 'adp',
        'bop': 'bop',
    }

    if ext in subdir_map:
        subdir = subdir_map[ext]
        subdir_path = pot_dir.joinpath(subdir).joinpath(target_name)
        if subdir_path.is_file():
            return Path(str(subdir_path))

    for subdir in subdir_map.values():
        try:
            subdir_traversable = pot_dir.joinpath(subdir).joinpath(target_name)
            if subdir_traversable.is_file():
                return Path(str(subdir_traversable))
        except (TypeError, FileNotFoundError):
            continue

    return Path(pot_name)

def cifread(cif_path: Union[str, Path]) -> Dict[str, Any]:
    """Read a CIF file and extract crystal structure information using ASE.

    Args:
        cif_path: Path to the CIF file.

    Returns:
        Dictionary containing lattice constants ('lat_a', 'lat_b', 'lat_c'),
        cell angles, chemical formula, and list of elements.
    """
    cif_path = Path(cif_path)
    filename = cif_path.stem

    atoms = ase_read(str(cif_path))
    if isinstance(atoms, list):
        atoms = atoms[0]
    cell = atoms.cell.cellpar()

    symbols = atoms.get_chemical_symbols()
    elements = list(dict.fromkeys(symbols))
    elem_comp = {el: symbols.count(el) for el in elements}

    return {
        'lat_a': float(cell[0]),
        'lat_b': float(cell[1]),
        'lat_c': float(cell[2]),
        'ang_a': float(cell[3]),
        'ang_b': float(cell[4]),
        'ang_g': float(cell[5]),
        'formula': atoms.get_chemical_formula(mode='hill'),
        'elements': elements,
        'elem_comp': elem_comp,
        'nelements': len(elements),
        'filename': filename
    }

def count_atomtypes(potential_filepath: Union[str, Path], elements: List[str]) -> Dict[str, int]:
    """Count the number of different atom types per element in a potential file.

    Args:
        potential_filepath: Path to the LAMMPS potential file.
        elements: List of element symbols to look for.

    Returns:
        Dictionary where keys are element names and values are the count of
        unique atom types for that element (e.g., {'C': 2} for C1, C2).
    """
    elem_type = {el: 0 for el in elements}
    str_path = str(potential_filepath)

    if str_path.lower().endswith(('.rebo', '.rebomos', '.airebo', '.meam', '.reaxff')):
        return {el: 1 for el in elements}

    pattern = re.compile(r'([A-Za-z]+)(\d*)')

    with open(potential_filepath, 'r', encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith('#') or not stripped_line:
            continue

        parts = stripped_line.split()
        for element in parts[:3]:
            match = pattern.match(element)
            if match:
                element_name = match.group(1)
                element_number = int(match.group(2)) if match.group(2) else 1
                if element_name in elem_type:
                    elem_type[element_name] = max(elem_type[element_name], element_number)
    return elem_type

def get_model_dimensions(lmp_path: Union[str, Path]) -> Dict[str, float | None]:
    """Read a LAMMPS data file and extract the simulation box dimensions.

    Args:
        lmp_path: Path to the LAMMPS data file.

    Returns:
        Dictionary containing the box dimensions with keys 'xlo', 'xhi',
        'ylo', 'yhi', 'zlo', 'zhi'.
    """
    dims: Dict[str, Optional[float]] = {k: None for k in ["xlo", "xhi", "ylo", "yhi", "zlo", "zhi"]}

    with open(lmp_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        for line in lines:
            if "xlo xhi" in line:
                dims["xlo"], dims["xhi"] = map(float, line.split()[0:2])
            elif "ylo yhi" in line:
                dims["ylo"], dims["yhi"] = map(float, line.split()[0:2])
            elif "zlo zhi" in line:
                dims["zlo"], dims["zhi"] = map(float, line.split()[0:2])
    return dims

def get_num_atom_types(lmp_path: Union[str, Path]) -> int:
    """Read a LAMMPS data file and extract the number of atom types.

    Args:
        lmp_path: Path to the LAMMPS data file.

    Returns:
        Number of atom types in the file.
    """
    with open(lmp_path, "r", encoding="utf-8") as f:
        for line in f:
            if "atom types" in line:
                return int(line.split()[0])
    return 1

def lj_params(atom_type_1: str, atom_type_2: str) -> Tuple[float, float]:
    """Calculate LJ parameters using Lorentz-Berthelot mixing rules.

    Pulls UFF parameters and applies mixing rules to determine interaction
    parameters between two atom types.

    Args:
        atom_type_1: Symbol of the first atom type (e.g., 'C').
        atom_type_2: Symbol of the second atom type (e.g., 'H').

    Returns:
        Tuple of (epsilon, sigma) - potential well depth and zero-potential distance.
    """
    e1 = lj.lj_params[atom_type_1][1]
    e2 = lj.lj_params[atom_type_2][1]
    s1 = lj.lj_params[atom_type_1][0]
    s2 = lj.lj_params[atom_type_2][0]
    epsilon = math.sqrt(e1 * e2)
    sigma = (s1 + s2) / 2
    return epsilon, sigma

def _remove_inline_comments(config: configparser.ConfigParser) -> configparser.ConfigParser:
    """Remove inline comments from a ConfigParser object.

    Args:
        config: The ConfigParser object to process.

    Returns:
        The object with inline comments removed.
    """
    for section in config.sections():
        for item in config.items(section):
            config.set(section, item[0], item[1].split("#")[0].strip())
    return config

def read_config(filepath: Union[str, Path]) -> Dict[str, Dict[str, Any]]:
    """Read a configuration file and return a dictionary with parsed values.

    Args:
        filepath: Path to the configuration file.

    Returns:
        Dictionary containing the parsed configuration parameters.
    """
    config = configparser.ConfigParser()
    config.read(filepath)
    config = _remove_inline_comments(config)

    params = {}
    for section in config.sections():
        params[section] = {}
        for key in config[section]:
            value = config.get(section, key)

            if value == '':
                params[section][key] = None
                continue

            if value.endswith(']'):
                try:
                    params[section][key] = json.loads(value)
                except json.JSONDecodeError:
                    cleaned = value.strip('[]')
                    items = [item.strip() for item in cleaned.split(',')]
                    parsed_items = []
                    for item in items:
                        if item.isdigit():
                            parsed_items.append(int(item))
                        elif item.replace('.', '', 1).replace('e', '', 1).replace('-', '', 1).isdigit():
                            parsed_items.append(float(item))
                        else:
                            parsed_items.append(item)
                    params[section][key] = parsed_items
            elif value.isdigit():
                params[section][key] = int(value)
            elif '.' in value and value.replace('.', '', 1).isdigit():
                params[section][key] = float(value)
            elif value.replace('.', '', 1).replace('e', '', 1).replace('-', '', 1).isdigit():
                params[section][key] = float(value)
            else:
                params[section][key] = value
    return params

def atomic2molecular(filepath: Union[str, Path]) -> None:
    """Convert a LAMMPS data file from atomic to molecular format in-place.

    Modifies the "Atoms" section of a LAMMPS data file, changing the style
    from 'atomic' to 'molecular' and adding the required molecule ID and
    charge/dipole fields.

    Args:
        filepath: Path to the LAMMPS data file to be modified.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    atoms_section = False
    modified_lines = []

    for line in lines:
        line = line.strip()

        if line.startswith("Velocities"):
            break

        if line == "Atoms # atomic":
            modified_lines.append("Atoms # molecular")
            atoms_section = True
            continue

        if atoms_section and line:
            parts = line.split()
            if len(parts) >= 4 and all(c in '0123456789.-+eE' for c in parts[0]):
                atom_id = parts[0]
                atom_type = parts[1]
                x, y, z = parts[2:5]
                new_line = f"{atom_id} 0 {atom_type} {x} {y} {z} 0 0 0"
                modified_lines.append(new_line)
                continue

        modified_lines.append(line)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("\n".join(modified_lines) + "\n")


def renumber_atom_types(filename: Union[str, Path], pot: Optional[List[str]] = None) -> None:
    """Renumber atom types in a LAMMPS data file to sequential order.

    Modifies a LAMMPS data file in-place to ensure atom types are numbered
    sequentially from 1. If a potential `pot` is provided, renumbers the types
    to match the order of elements in that list.

    Args:
        filename: Path to the LAMMPS data file to be modified.
        pot: List of element symbols in the desired order for renumbering.
    """
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    masses_section = False
    atom_types = {}

    for i, line in enumerate(lines):
        if line.strip() == 'Masses':
            masses_section = True
            continue

        if masses_section:
            if 'Atoms' in line:
                break

            parts = line.split()
            if len(parts) < 2:
                continue

            atom_type_id = int(parts[0])
            mass = float(parts[1])
            if '#' in line:
                atom_type_name = line.split('#')[-1].strip()
                lines[i] = ''
            else:
                atom_type_name = f'Unknown_{atom_type_id}'
            atom_types[atom_type_id] = (atom_type_name, mass)

    modified_lines = set()
    mod_lines = {}
    elem_pot = {}
    elem = {}
    type_offset = len(atom_types) if pot is not None else 1
    current_type = 1

    for i in range(1, len(atom_types)+1):
        atoms_section = False
        if pot is not None:
            current_type = i
        for line_idx, line in enumerate(lines):
            stripped_line = line.strip()

            if 'Atoms' in line:
                atoms_section = True
                continue

            if atoms_section and stripped_line and line_idx not in modified_lines:
                parts = stripped_line.split()

                if parts[1] == str(i):
                    parts[1] = parts[0] = str(current_type)
                    lines[line_idx] = ''
                    mod_lines[current_type] = '  '.join(parts) + '\n'
                    modified_lines.add(line_idx)
                    elem[current_type] = atom_types[i]
                    current_type += type_offset

    if pot is not None:
        atom_idx = 1
        atom_lines = {}
        for element in pot:
            for line_num in range(1, len(mod_lines)+1):
                stripped_line = mod_lines[line_num].strip()
                parts = stripped_line.split()
                if elem[int(parts[1])][0] == element:
                    elem_pot[atom_idx] = elem[int(parts[1])]
                    parts[1] = str(atom_idx)
                    atom_lines[atom_idx] = '  '.join(parts) + '\n'
                    atom_idx += 1
        elem = elem_pot
        mod_lines = atom_lines

    masses_section = False
    for i, line in enumerate(lines):
        if re.match(r'^\s*\d+\s+atom types\s*$', line.strip()):
            lines[i] = f"  {len(elem)}  atom types\n"
            continue

        if line.strip() == 'Masses':
            masses_section = True
            continue

        if masses_section:
            for atom_type_id in range(1, len(elem)+1):
                lines[i] += f"{atom_type_id} {elem[atom_type_id][1]}  #{elem[atom_type_id][0]}\n"
            break

    with open(filename, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    with open(filename, 'a', encoding='utf-8') as f:
        for line in mod_lines.values():
            f.write(line)

def check_potential_cif_compatibility(cif_path: Union[str, Path],
                                        pot_path: Union[str, Path]) -> float:
    """Check if the number of atom types per element is compatible.

    Compares the number of atom types for each element defined in a CIF file
    versus a potential file. Returns a multiplier if the potential defines
    a consistent multiple of atom types compared to the CIF.

    Args:
        cif_path: Path to the CIF file.
        pot_path: Path to the potential file.

    Returns:
        The consistent ratio of atom types in the potential vs. the CIF.

    Raises:
        ValueError: If the ratio of atom types is not consistent across all elements.
    """
    cif_data = cifread(cif_path)
    potentials_count = count_atomtypes(pot_path, cif_data['elements'])

    multiples = {
        element: (potentials_count.get(element, 0) / cif_count
                    if cif_count > 0 and potentials_count.get(element, 0) != 1 else 1)
        for element, cif_count in cif_data['elem_comp'].items()
    }

    unique_multiples = set(multiples.values())
    if len(unique_multiples) > 1:
        raise ValueError(
            f'Inconsistent atom type multiplier between potential and CIF file. '
            f'Ratios found: {unique_multiples}'
        )

    return unique_multiples.pop()
