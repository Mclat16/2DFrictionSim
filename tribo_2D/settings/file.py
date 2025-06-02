def init(f):
    f.writelines([
    "# LAMMPS input script for system build with input of substrate, graphene sheet and AFM tip\n\n",
    "clear\n\n",
    
    "units           metal\n",
    "atom_style      atomic\n",
    "neighbor        0.3 bin\n",
    "neigh_modify    every 1 delay 0 check yes #every 5\n\n",
    
    "boundary   	    p p f\n"
    ])

def init_mol(f):
    f.writelines([
    "# LAMMPS input script for system build with input of substrate, graphene sheet and AFM tip\n\n",
    "clear\n\n",
    
    "units           metal\n",
    "atom_style      molecular\n",
    "neighbor        0.3 bin\n",
    "neigh_modify    every 1 delay 0 check yes #every 5\n\n",
    
    "boundary   	    p p f\n"
    ])
    
def thermo_afm(f):

    f.writelines([
    ])

def min(f):
    pass
