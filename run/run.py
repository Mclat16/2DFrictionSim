
"""
This script runs the AFM and sheet simulations for all materials
listed in the input list.

"""

import os
from tribo_2D import afm, sheet

with open("run/material_list.txt", "r", encoding="utf-8") as f:
    materials = [line.strip() for line in f]

with open("run/afm_config_temp.ini", "r", encoding="utf-8") as file:
    template_afm = file.read()

with open("run/sheet_config_temp.ini", "r", encoding="utf-8") as file:
    template_sheet = file.read()


for m in materials:
    updated_afm = template_afm.replace("{mat}", m)

    with open("run/afm_config.ini", "w", encoding="utf-8") as file:
        file.write(updated_afm)

    updated_sheet = template_sheet.replace("{mat}", m)
    with open("run/sheet_config.ini", "w", encoding="utf-8") as file:
        file.write(updated_sheet)

    run = afm.AFM('run/afm_config.ini')
    run.system()
    run.slide()
    # run.pbs()

    run = sheet.sheetvsheet('sheet_config.ini')
    # run.system()
    # run.pbs()

for file in os.listdir():
    if file.endswith(".cif") or file.endswith(".lmp") or file.endswith(".json"):
        os.remove(file)
