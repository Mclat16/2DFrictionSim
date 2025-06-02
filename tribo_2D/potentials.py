from ase import data
from .tools import *


def sheet(var,filename,layer,sheetvsheet=False):
    """Writes the LAMMPS input file content to the specified filename.
    Args:
    filename (str): The name of the file to write to.
    """    
    with open(filename, 'w') as f:
        
        group_def = {}
        elemgroup = {}
        potentials= {}
        
        arr = {}
        count = {}

        i=0    
        for element, count in var['pot']['2D'].items():
            if not count or count == 1:
                arr[i] = element
                i+=1
            else:
                for t in range(1,count+1):
                    arr[i] = element + str(t)
                    i+=1

        i = 0 
        c = 0
        g = 0
        for element,count in var['pot']['2D'].items():
            i += c
            for l in range(layer):
                for t in range(1,count+1):
                    n = i + t
                    m = element
                    g+=1
                    group_def.update({g: [f"2D_l{l+1}_t{n}", str(g),str(m),arr[n-1],l+1]})
                    elemgroup.setdefault(l, {}).setdefault(m, []).append(g)
                    c = count

        for m in var['data']['2D']['elem_comp']: 
                mass=data.atomic_masses[data.atomic_numbers[m]] 
                f.write(f"mass {elemgroup[0][m][0]}*{elemgroup[layer-1][m][-1]} {mass} #{m}\n")
        
        for l in range(layer):
            layer_g = [group_def[i][1] for i in range(1,var['data']['2D']['natype']*layer+1) if "2D_l"+str(l+1) in group_def[i][0]]
            f.write(f"group layer_{l+1} type {' '.join(layer_g)}\n")
        
        f.write(f"pair_style hybrid {(var['2D']['pot_type']+' ') * layer} lj/cut 11.0\n")

        for l in range(layer):
            potentials[l] = [
                group_def[i][3] if group_def[i][4]==l+1 else "NULL"
                for i in range(1,var['data']['2D']['natype']*layer+1)
            ]            
            f.write(f"pair_coeff * * {var['2D']['pot_type']} {l+1} {var['pot']['path']['2D']} {'  '.join(potentials[l])} # interlayer '2D' Layer {l+1}\n")
        
        if sheetvsheet:
            for t in var['data']['2D']['elem_comp']:
                for s in var['data']['2D']['elem_comp']:
                    e,sigma = LJparams(s,t)
                    for l in range(3):
                        t1 = f"{elemgroup[l][t][0]}*{elemgroup[l][t][-1]}"
                        t2 = f"{elemgroup[l+1][s][0]}*{elemgroup[l+1][s][-1]}"
                        if elemgroup[l][t][0] == elemgroup[l][t][-1]:
                            t1 = f"{elemgroup[l][t][0]}"
                        if elemgroup[l+1][s][0] == elemgroup[l+1][s][-1]:
                            t2 = f"{elemgroup[l+1][s][0]}"
                        if elemgroup[l][t][0]>elemgroup[l+1][s][0]:
                            t1, t2 = t2, t1
                        f.write(f"pair_coeff {t1} {t2} lj/cut {e} {sigma} \n")
                    
                    index_pairs = [(1, 3), (0, 3), (0, 2)]
                    for i,j in index_pairs:
                        t1 = f"{elemgroup[i][t][0]}*{elemgroup[i][t][-1]}"
                        t2 = f"{elemgroup[j][s][0]}*{elemgroup[j][s][-1]}"
                        if elemgroup[i][t][0] == elemgroup[i][t][-1]:
                            t1 = f"{elemgroup[l][t][0]}"
                        if elemgroup[j][s][0] == elemgroup[j][s][-1]:
                            t2 = f"{elemgroup[l+1][s][0]}"
                        if elemgroup[i][t][0]>elemgroup[j][s][0]:
                            t1, t2 = t2, t1
                        f.write(f"pair_coeff {t1} {t2} lj/cut 1e-100 {sigma} \n")

        else:
            if var['2D']['pot_type'] == 'sw':
                for t in var['data']['2D']['elem_comp']:
                    for s in var['data']['2D']['elem_comp']:
                        e,sigma = LJparams(s,t)
                        for l in range(layer-1):
                            t1 = f"{elemgroup[l][t][0]}*{elemgroup[l][t][-1]}"
                            t2 = f"{elemgroup[l+1][s][0]}*{elemgroup[layer-1][s][-1]}"
                            if elemgroup[l][t][0] == elemgroup[l][t][-1]:
                                t1 = f"{elemgroup[l][t][0]}"
                            if elemgroup[l+1][s][0] == elemgroup[layer-1][s][-1]:
                                t2 = f"{elemgroup[l+1][s][0]}"
                            if elemgroup[l][t][0]>elemgroup[l+1][s][0]:
                                t1, t2 = t2, t1
                            f.write(f"pair_coeff {t1} {t2} lj/cut {e} {sigma} \n")
        
def afm(var,layer):

    """Writes the LAMMPS input file content to the specified filename.
    Args:
    filename (str): The name of the file to write to.
    """
    filename = f"{var['dir']}/l_{layer}/lammps/system.in.settings"
    with open(filename, 'w') as f:
        group = ['sub','tip','2D']

        arr = {}
        count = {}
        elemgroup = {}
        group_def = {}
        g = 1
        for gr in group:
            arr[gr] = {}
            i=0
            for element, count in var['pot'][gr].items():
                if not count or count == 1:
                    arr[gr][i] = element
                    i+=1
                else:
                    for t in range(1,count+1):
                        arr[gr][i] = element + str(t)
                        i+=1
        for gr in group:
            i=0
            c=0
            for element,count in var['pot'][gr].items():
                i += c
                if gr == '2D':
                    for l in range(layer):
                        for t in range(1,count+1):
                            n = i + t
                            m = element
                            mass=data.atomic_masses[data.atomic_numbers[m]] 
                            group_def.update({g: [f"{gr}_l{l+1}_t{n}", str(g),str(m),arr[gr][n-1],l+1]})
                            elemgroup.setdefault(gr, {}).setdefault(l, {}).setdefault(m, []).append(g)
                            c = count
                            g+=1

                else:
                    for t in range(1,count+1):
                        n = i + t
                        m = element
                        group_def.update({
                        g:   [f"{gr}_b_t{t+1}", str(g), str(m),      arr[gr][n-1]],
                        g+1: [f"{gr}_fix_t{t+1}", str(g+1), str(m),    arr[gr][n-1]],
                        g+2: [f"{gr}_thermo_t{t+1}", str(g+2), str(m), arr[gr][n-1]]
                        })         
                        elemgroup.setdefault(gr, {}).setdefault(m, []).extend([g, g+1, g+2]) 
                        g+=3
                        c = count
        for gr in group:
            for m in var['data'][gr]['elem_comp']: 
                mass=data.atomic_masses[data.atomic_numbers[m]] 
                if gr =='2D':
                    f.write(f"mass {elemgroup[gr][0][m][0]}*{elemgroup[gr][layer-1][m][-1]} {mass} #{m} {gr}\n")
                else:
                    f.write(f"mass {elemgroup[gr][m][0]}*{elemgroup[gr][m][-1]} {mass} #{m} {gr}\n")
                

        for gr in group:     
            all = [group_def[i][1] for i in range(1,var['ngroups'][layer]+1) if gr in group_def[i][0]]
            f.write(f"group {gr}_all type {' '.join(all)}\n")   
            if gr == 'sub' or gr == 'tip':
                for n in ["_fix", "_thermo"]:
                    sub_group = [group_def[i][1] for i in range(1,var['ngroups'][layer]+1) if gr+n in group_def[i][0]]
                    f.write(f"group {gr}{n} type {' '.join(sub_group)}\n")
            if gr == '2D':
                for l in range(layer):
                    layer_g = [group_def[i][1] for i in range(1,var['ngroups'][layer]+1) if "2D_l"+str(l+1) in group_def[i][0]]
                    f.write(f"group layer_{l+1} type {' '.join(layer_g)}\n")

        f.writelines(["group mobile union tip_thermo sub_thermo\n",
                f"pair_style hybrid {var['sub']['pot_type']} {var['tip']['pot_type']} {(var['2D']['pot_type'] + ' ') * layer} lj/cut 8.0\n"])
        
        potentials = {}
        t=0
        for g in group:
            t+=1
            if g == '2D':
                for l in range(layer):
                    potentials[l] = [
                        group_def[i][3] if "2D_l"+str(l+1) in group_def[i][0] else "NULL"
                        for i in range(1,var['ngroups'][layer]+1)
                    ]     

                    f.write(f"pair_coeff * * {var['2D']['pot_type']} {t+l} {var['pot']['path']['2D']} {'  '.join(potentials[l])} # interlayer '2D' Layer {l+1}\n")
            else:
                potentials[g]=[group_def[i][2] if g in group_def[i][0] else "NULL"
                                for i in range(1,var['ngroups'][layer]+1)]
                f.write(f"pair_coeff * * {var[g]['pot_type']} {t} {var['pot']['path'][g]} {'  '.join(potentials[g])} # interlayer {g.capitalize()}\n")
        
        h = 0
        for t in var['data']['2D']['elem_comp']:    
            for key in ('sub','tip'):
                for s in var['data'][key]['elem_comp']:
                    e,sigma = LJparams(t,s)
                    if key == 'sub' and sigma>h:
                        h = sigma
                    if len(elemgroup['2D'][layer-1][t]) == 1 and layer == 1:
                        f.write(f"pair_coeff {elemgroup[key][s][0]}*{elemgroup[key][s][-1]} {elemgroup['2D'][0][t][0]} lj/cut {e} {sigma}\n")
                    else:  
                        f.write(f"pair_coeff {elemgroup[key][s][0]}*{elemgroup[key][s][-1]} {elemgroup['2D'][0][t][0]}*{elemgroup['2D'][layer-1][t][-1]} lj/cut {e} {sigma}\n")
            if layer>1:
                for s in var['data']['2D']['elem_comp']:
                    e,sigma = LJparams(s,t)
                    for l in range(layer-1):
                        t1 = f"{elemgroup['2D'][l][t][0]}*{elemgroup['2D'][l][t][-1]}"
                        t2 = f"{elemgroup['2D'][l+1][s][0]}*{elemgroup['2D'][layer-1][s][-1]}"
                        if elemgroup['2D'][l][t][0] == elemgroup['2D'][l][t][-1]:
                            t1 = f"{elemgroup['2D'][l][t][0]}"
                        if elemgroup['2D'][l+1][s][0] == elemgroup['2D'][layer-1][s][-1]:
                            t2 = f"{elemgroup['2D'][l+1][s][0]}"
                        if elemgroup['2D'][l][t][0]>elemgroup['2D'][l+1][s][0]:
                            t1, t2 = t2, t1
                        f.write(f"pair_coeff {t1} {t2} lj/cut {e} {sigma} \n")
        for s in var['data']['sub']['elem_comp']:
            for t in var['data']['tip']['elem_comp']:
                e,sigma = LJparams(s,t)
                f.write(f"pair_coeff {elemgroup['sub'][t][0]}*{elemgroup['sub'][t][-1]} {elemgroup['tip'][t][0]}*{elemgroup['tip'][t][-1]}  lj/cut {e} {sigma} \n")

    return h
def single_body_3layer(var,filename,system):
    
    group_def = {}
    elemgroup = {}
    potentials= {}
    arr = []
    i=0  
    c = 0  

    with open(filename, 'w') as f:

        for element, count in var['pot'][system].items():
            i += c
            if not count or count == 1:
                arr.append(element)
            else:
                for t in range(1,count+1):
                    arr.append(element + str(t))
        
            for t in range(1,count+1):
                n = i + t
                group_def.update({n: [f"{system}_t{n}", str(n),str(element),arr[n-1]]})
                group_def.update({n+1: [f"{system}_fix_t{n}", str(n+1),str(element),arr[n-1]]})
                group_def.update({n+2: [f"{system}_thermo_t{n}", str(n+2),str(element),arr[n-1]]})
                elemgroup.setdefault(element, []).extend([n,n+1,n+2])
                i+=3
                c = count

    
        for m in var['data'][system]['elem_comp']: 
            mass=data.atomic_masses[data.atomic_numbers[m]] 
            f.write(f"mass {elemgroup[m][0]}*{elemgroup[m][-1]} {mass} #{m}\n")
        
        potentials = [group_def[i][2] for i in range(1,var['data'][system]['natype']+1)]
                    
        f.writelines([
            f"pair_style {var[system]['pot_type']}\n",
            f"pair_coeff * * {var['pot']['path'][system]} {' '.join((potentials))}\n"])
        

def single_body(var,filename,system):
    
    group_def = {}
    elemgroup = {}
    potentials= {}
    arr = []
    i=0  
    c = 0  

    with open(filename, 'w') as f:

        for element, count in var['pot'][system].items():
            i += c
            if not count or count == 1:
                arr.append(element)
            else:
                for t in range(1,count+1):
                    arr.append(element + str(t))
        
            for t in range(1,count+1):
                n = i + t
                group_def.update({n: [f"{system}_t{n}", str(n),str(element),arr[n-1]]})
                elemgroup.setdefault(element, []).append(n)
                i+=1
                c = count

    
        for m in var['data'][system]['elem_comp']: 
            mass=data.atomic_masses[data.atomic_numbers[m]] 
            if len(elemgroup[m])==1:
                f.write(f"mass {elemgroup[m][0]} {mass} #{m}\n")
            else:
                f.write(f"mass {elemgroup[m][0]}*{elemgroup[m][-1]} {mass} #{m}\n")
        
        potentials = [group_def[i][2] for i in range(1,len(arr)+1)]
                    
        f.writelines([
            f"pair_style {var[system]['pot_type']}\n",
            f"pair_coeff * * {var['pot']['path'][system]} {' '.join((potentials))}\n"])
        