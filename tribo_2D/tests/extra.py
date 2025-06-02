from ..tools import *
from ..settings import *
from ..potentials import *
from ..build import *
from ase import data
import subprocess
import os
from lammps import lammps
import numpy as np
import re
from pathlib import Path

def sub_build2(var):
    
    filename = f"{var['sub']['mat']}.lmp"
    settings = f"sub.in.settings"
    settings_sb(var,settings,'sub')

    if var['sub']['amorph'] == 'a':
        
        am_filename = os.path.join(os.path.dirname(__file__), "materials", f"amor_{filename}")
        filename = os.path.join(os.path.dirname(__file__), "materials", f"{var['sub']['mat']}.lmp")

        if os.path.exists(am_filename):
            print("File exists")
        else:
            slab_generator('sub',var, 200, 200, 20)
            amorph2('sub',filename, am_filename,2500,var)
            
            os.remove(filename)
            print("File Removed")
        
        filename = am_filename
    
    else:
        slab_generator('sub',var['2D']['x'],'sub',var['2D']['y'],10)
        filename = os.path.join(os.path.dirname(__file__), "materials", f"{var['sub']['mat']}.lmp")

    with open("sub_input.lmp", 'w') as f:

        f.writelines([
            "boundary p p p\n",
            "units metal\n",
            "atom_style      atomic\n",
            f"region box block {var['dim']['xlo']} {var['dim']['xhi']} {var['dim']['ylo']} {var['dim']['yhi']} -50 50\n",
            f"create_box       {var['data']['sub']['natype']} box\n\n",
            f"read_data {filename} add append\n",
            f"include {settings}\n",
            "group sub region box\n",
            "group box subtract all sub\n",
            "delete_atoms group box\n",
            f"change_box all x final 0 {var['dim']['xhi']} y final 0 {var['dim']['yhi']} z final 0 10\n\n",

            "#Identify bottom atoms of Amorphous Silicon substrate\n\n",
            "region          sub_fix block INF INF INF INF INF 2 units box\n",
            "group           sub_fix region sub_fix\n\n",
            "#Identify thermostat region of Amorphous Silicon substrate\n\n",
            "region          sub_thermo block INF INF INF INF 2 5 units box\n",
            "group           sub_thermo region sub_thermo\n\n",

            "# Define sub groups and atom types\n\n"
            ])

        for t in range(var['data']['sub']['natype']):
            t+=1
            f.write(f"group sub_{t} type {t}\n")

        i=1
        for t in range(var['data']['sub']['natype']):
            t+=1
            f.writelines([
                f"set group sub_{t} type {i}\n",

                f"group sub_fix_{t} intersect sub_fix sub_{t}\n",
                f"set group sub_fix_{t} type {i+1}\n",
                f"group sub_fix_{t} delete\n\n",

                f"group sub_thermo_{t} intersect sub_thermo sub_{t}\n",
                f"set group sub_thermo_{t} type {i+2}\n",
                f"group sub_thermo_{t} delete\n\n"

                f"group sub_{t} delete\n\n"
            ])

            i+=3

        f.write(f"write_data      {var['dir']}/system_build/sub.lmp")




def amorph2(system,filename,am_filename, tempmelt,var):
    
    quench = (tempmelt-var['general']['temproom'])*100
    # lmp = lammps(cmdargs=["-log", "none", "-screen", "none",  "-nocite"])
    settings = f"sub.in.settings"
    settings_ob(var,settings,system)
    with open("amorph_input.lmp", 'w') as f:
        f.writelines([
            "boundary p p p\n",
            "units metal\n",
            "atom_style      atomic\n\n",

            f"read_data {filename}\n\n", 
            #------------------Apply potentials-----------------------
            f"include {settings}\n\n",
            ##########################################################
            #-------------------Energy Minimization------------------#
            ##########################################################
            "min_style       cg\n",
            "minimize        1.0e-4 1.0e-8 100 1000\n",
            ##########################################################
            #-------------------Equilibrate System-------------------#
            ##########################################################
            "timestep        0.001\n",
            "thermo          100\n",
            "thermo_style    custom step temp pe ke etotal press\n",
            # Specify melting temperature and timestep
            f"velocity        all create {tempmelt} 1234579 rot yes dist gaussian\n",
            "run             0\n",
            # Equilibration at temperature
            f"fix             melt all nvt temp {tempmelt} {tempmelt} $(100.0*dt)\n",
            "run             5000\n",
            "unfix           melt\n",

            ##########################################################
            #----------------------Quench System---------------------#
            ##########################################################
            f"fix             quench all nvt temp {tempmelt} {var['general']['temproom']} $(100.0*dt)\n ",
            f"run             {quench}\n ",
            "unfix           quench \n",
            f"write_data {am_filename}"
        ])