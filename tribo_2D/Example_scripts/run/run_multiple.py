from tribo_2D.afm import *
from tribo_2D.tools import *
from tribo_2D.sheet import *
import os

with open("run/material_list.txt", "r") as f:
    materials = [line.strip() for line in f]

with open(f"run/afm_config_temp.ini", "r") as file:
    template_afm = file.read()

# with open(f"run/sheet_config_temp.ini", "r") as file:
#     template_sheet = file.read()

# materials = ["t-MnS2"]

for m in materials:
    updated_afm = template_afm.replace("{mat}", m)

    with open(f"run/afm_config.ini", "w") as file:
        file.write(updated_afm)

    # updated_sheet = template_sheet.replace("{mat}", m)
    # with open(f"run/sheet_config.ini", "w") as file:
    #     file.write(updated_sheet)

    run=afm('run/afm_config.ini')
    run.system()
    run.slide()
    # run.pbs()

    # run=sheetvsheet('sheet_config.ini')
    # run.sheet_system()
    # run.sheet_pbs()

for file in os.listdir():
    if file.endswith(".cif") or file.endswith(".lmp") or file.endswith(".json"):
        os.remove(file)