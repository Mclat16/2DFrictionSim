"""
This set of tools deals with the reading, writing, modification and processing of files
"""

import os
import json
import re
import shutil
import configparser
import numpy as np

from tribo_2D import settings, Potentials


def cifread(cif):
    """
    Reads a CIF file and extracts important information on the crystal structure.
    Args:
        cif (str): Path to the CIF file.
    Returns:
        cif(dict): A dictionary containing the extracted information such as
        lattice constants, cell angles, chemical formula, and elements.
    """
    filename = os.path.basename(cif).split('.')[0]

    with open(cif, 'r', encoding="utf-8") as f:
        lines = f.readlines()

    elements = []
    cif = {}
    reading_elements = False
    header_skipped = False
    keys = {
        '_cell_length_a': 'lat_a',
        '_cell_length_b': 'lat_b',
        '_cell_length_c': 'lat_c',
        '_chemical_formula_structural': 'formula',
        '_cell_angle_alpha': 'ang_a',
        '_cell_angle_beta': 'ang_b',
        '_cell_angle_gamma': 'ang_g'
    }

    for line in lines:
        for key, var in keys.items():
            if line.startswith(key):
                value = line.split(maxsplit=1)[1].strip()
                cif[var] = float(value) if 'formula' not in var else value

        if line.strip().startswith('_atom_site_type_symbol'):
            reading_elements = True
            continue

        if reading_elements and not header_skipped:
            if line.strip().startswith('_'):
                continue
            header_skipped = True

        if reading_elements and header_skipped:
            parts = line.strip().split()
            if parts:
                element = parts[0]
                elements.append(element)

    elem_count = {}
    if cif.get('formula'):
        matches = re.findall(r'([A-Z][a-z]*)(\d*)', cif['formula'])
        for element, count in matches:
            elem_count[element] = int(count) if count else 1
        nelements = len(elements)

        cif.update({
            "elements": elements,
            "elem_comp": elem_count,
            "nelements": nelements,
            "filename": filename
        })

    return cif


def count_elemtypes(file):

    elem_type = {}

    matches = re.compile(r'([A-Za-z]+)(\d*)')

    with open(file, 'r') as f:
        lines = f.readlines()

    for line in lines:
        stripped_line = line.strip()

        if stripped_line.startswith('#') or not stripped_line:
            continue

        parts = stripped_line.split()

        if len(parts) >= 3:
            for element in parts[:3]:
                match = matches.match(element)
                if match:
                    element_name = match.group(1)
                    element_number = match.group(2)

                    if element_number:
                        element_number = int(element_number)

                    else:
                        element_number = 1

                    if element_name not in elem_type:
                        elem_type[element_name] = 0

                    elem_type[element_name] = max(
                        elem_type[element_name], element_number)

    return elem_type


def get_model_dimensions(lmp):
    xlo, xhi, ylo, yhi, zlo, zhi = [None] * 6
    with open(lmp, "r") as f:
        lines = f.readlines()
        for line in lines:
            if "xlo xhi" in line:
                xlo, xhi = map(float, line.split()[0:2])
            elif "ylo yhi" in line:
                ylo, yhi = map(float, line.split()[0:2])
            elif "zlo zhi" in line:
                zlo, zhi = map(float, line.split()[0:2])
    dim = {
        "xlo": xlo,
        "xhi": xhi,
        "ylo": ylo,
        "yhi": yhi,
        "zlo": zlo,
        "zhi": zhi
    }
    return dim


def LJparams(X, Y):
    # Lorentz-Bertholt Mixing rules for obtaining the LJ parameters between two atoms using the Universal Force Field parameters
    e1 = lj_params[X][1]
    e2 = lj_params[Y][1]
    s1 = lj_params[X][0]
    s2 = lj_params[Y][0]
    epsilon = np.sqrt(e1*e2)
    sigma = (s1 + s2)/2
    return epsilon, sigma


def removeInlineComments(config):

    for section in config.sections():
        for item in config.items(section):
            config.set(section, item[0], item[1].split("#")[0].strip())
    return config


def read_config(input):
    config = configparser.ConfigParser()
    config.read(input)

    config = removeInlineComments(config)

    var = {}
    for section in config.sections():
        var[section] = {}
        for key in config[section]:
            value = config.get(section, key)

            if value.endswith(']'):
                var[section][key] = json.loads(value)
            elif value.isdigit():
                var[section][key] = int(value)
            elif '.' in value and value.replace('.', '', 1).isdigit():
                var[section][key] = float(value)
            elif value.replace('.', '', 1).replace('e', '', 1).replace('-', '', 1).isdigit():
                var[section][key] = float(value)
            else:
                var[section][key] = value
    return var


def atomic2molecular(file):
    with open(file, 'r') as f:
        lines = f.readlines()

    atoms_section = False  # Track when we are inside the "Atoms" section
    modified_lines = []

    for line in lines:
        line = line.strip()
        # If we hit the Velocities section, stop processing further lines.
        if line.startswith("Velocities"):
            break
        # Replace "Atoms # atomic" with "Atoms # molecular"
        if line == "Atoms # atomic":
            modified_lines.append("Atoms # molecular")
            atoms_section = True  # Start processing atom lines
            continue

        # Modify atom data lines
        if atoms_section and line:
            parts = line.split()
            if len(parts) >= 4:  # Ensure we have at least ID, type, and coordinates
                atom_id = parts[0]
                atom_type = parts[1]
                x, y, z = parts[2:5]

                # Insert a zero between atom ID and atom type, and add three zeros at the end
                new_line = f"{atom_id} 0 {atom_type} {x} {y} {z} 0 0 0"
                modified_lines.append(new_line)
                continue

        # Add unmodified lines to the list
        modified_lines.append(line)

    # Overwrite the original file with the modified content
    with open(file, 'w') as f:
        f.write("\n".join(modified_lines) + "\n")


def copy_file(path1, dest):

    os.makedirs(dest, exist_ok=True)

    filename = os.path.basename(path1)

    path2 = os.path.join(dest, filename)

    shutil.copy2(path1, path2)

    return path2


def num_atoms_lmp(filename):
    with open(filename, 'r') as file:
        lines = file.readlines()

    modified_lines = []
    masses_section = False
    atoms_section = False
    a = 1

    atom_types = {}
    elem = {}
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

    for i in range(1, len(atom_types)+1):
        atoms_section = False
        for l, line in enumerate(lines):
            stripped_line = line.strip()

            if 'Atoms' in line:
                atoms_section = True
                continue
            if atoms_section and stripped_line and l not in modified_lines:
                parts = stripped_line.split()
                if parts[1] == str(i):
                    parts[1] = str(a)  # Update atom type
                    lines[l] = '  '.join(parts) + '\n'
                    modified_lines.add(l)
                    elem[a] = atom_types[i]
                    a += 1  # Increment for next line
                    continue

    masses_section = False
    for i, line in enumerate(lines):
        if re.match(r'^\s*\d+\s+atom types\s*$', line.strip()):
            lines[i] = f"  {len(elem)}  atom types\n"
            continue

        if line.strip() == 'Masses':
            masses_section = True
            continue

        if masses_section:
            for l in range(1, len(elem)+1):
                lines[i] += f"{l} {elem[l][1]}  #{elem[l][0]}\n"
            break

    # Save modified file
    with open(filename, 'w') as file:
        file.writelines(lines)


def process_h(pot, filename):
    with open(filename, 'r') as f:
        lines = f.readlines()

    masses_section = False
    atoms_section = False

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

    # Update atom types
    modified_lines = set()
    mod_lines = {}
    pre_elem = {}
    elem = {}
    # for i in range(1,len(atom_types)+1):
    for i in range(1, len(atom_types)+1):
        atoms_section = False
        t = i
        for l, line in enumerate(lines):
            stripped_line = line.strip()

            if 'Atoms' in line:
                atoms_section = True
                continue

            if atoms_section and stripped_line and l not in modified_lines:
                parts = stripped_line.split()

                if parts[1] == str(i):
                    parts[1] = parts[0] = str(t)
                    lines[l] = ''
                    mod_lines[t] = '  '.join(parts) + '\n'
                    modified_lines.add(l)
                    pre_elem[t] = atom_types[i]
                    t += len(atom_types)

    a = 1
    atom_lines = {}
    for i in pot:

        atoms_section = False
        for l in range(1, len(mod_lines)+1):

            stripped_line = mod_lines[l].strip()

            parts = stripped_line.split()

            if pre_elem[int(parts[1])][0] == i:
                elem[a] = pre_elem[int(parts[1])]
                parts[1] = str(a)
                atom_lines[a] = '  '.join(parts) + '\n'
                a += 1

    # Update atom types line
    masses_section = False
    for i, line in enumerate(lines):
        if re.match(r'^\s*\d+\s+atom types\s*$', line.strip()):
            lines[i] = f"  {len(elem)}  atom types\n"
            continue

        if line.strip() == 'Masses':
            masses_section = True
            continue

        if masses_section:
            for l in range(1, len(elem)+1):
                lines[i] += f"{l} {elem[l][1]}  #{elem[l][0]}\n"
            break

    # Write updated file
    with open(filename, 'w') as f:
        f.writelines(lines)
    with open(filename, 'a') as f:  # 'a' means append mode
        for line in atom_lines.values():
            f.write(line)
