"""
AFM simulation module for generating simulation cells and input files
for the Prandtl-Tomlinson model in LAMMPS.

This module handles configuration parsing, structure building
(2D material, substrate, tip), potential assignment, and directory
setup for AFM simulations.
"""

from pathlib import Path
import numpy as np
from tribo_2D import tools, build, potentials, settings


class AFM:
    """
    A class to generate a simulation cell for the Prandtl-Tomlinson
    model in LAMMPS simulations.

    This class reads configuration data, materials, and potential files,
    builds the necessary atomic structures (e.g., 2D material, substrate, tip),
    and prepares the directory structure and scripts needed for
    simulation setup, execution, and post-processing.

    """

    def __init__(self, input_file):
        """
        Initialize the AFM simulation setup using an .INI configuration file.

        Args:
            input_file (str): Path to the input configuration file.
        """
        # --- Read and parse configuration ---
        var = tools.read_config(input_file)
        self.parts = ['2D', 'sub', 'tip']

        # --- Read material and potential data ---
        var['data'] = {
            p: tools.cifread(var[p]['cif_path']) for p in self.parts}
        var['pot'] = {
            p: tools.count_elemtypes(var[p]['pot_path']) for p in self.parts}

        # --- Count atom types per part ---
        for part in self.parts:
            ntypes = sum(var['pot'][part].values())
            var['data'][part]['natype'] = ntypes if part == '2D' else ntypes*3
            # x3 for thermo/fixed layers in sub and tip

        # --- Set up working directory structure ---
        var['dir'] = (
            f"{var['2D']['mat']}/afm/"
            f"{var['2D']['x']}x_{var['2D']['y']}y/"
            f"sub_{var['sub']['amorph']}{var['sub']['mat']}_"
            f"tip_{var['tip']['amorph']}{var['tip']['mat']}_"
            f"r{var['tip']['r']}/K{var['general']['temproom']}"
        )
        self.scripts = f"{var['dir']}/scripts"
        for subdir in ["visuals", "results", "build", "potentials"]:
            Path(var['dir'], subdir).mkdir(parents=True, exist_ok=True)

        # --- Copy potential files ---
        var['pot']['path'] = {
            p: tools.copy_file(var[p]['pot_path'], f"{var['dir']}/potentials/")
            for p in self.parts
        }

        # --- Build 2D material and expand layers ---
        self.var = build.sheet(var)
        self.var['ngroups'] = {}
        self.directory = {}
        for layer in self.var['2D']['layers']:
            layer_dir = Path(self.var['dir']) / f"l_{layer}"
            self.directory[layer] = layer_dir
            for sub in ["data", "lammps"]:
                (layer_dir / sub).mkdir(parents=True, exist_ok=True)
            if layer > 1:
                build.stacking(self.var, layer)
            self.var['ngroups'][layer] = (
                self.var['data']['2D']['natype'] * layer +
                self.var['data']['sub']['natype'] +
                self.var['data']['tip']['natype']
            )

        # --- Set scan angles and dump intervals ---
        self.scan_angle = np.arange(
            self.var['general']['scan_angle'][0],
            self.var['general']['scan_angle'][1] + 1,
            self.var['general']['scan_angle'][2]
        )
        self.dump_load = [
            self.var['general']['force'][i]
            for i in range(4, len(self.var['general']['force']), 5)
        ]
        self.dump_slide = [
            self.scan_angle[i]
            for i in range(4, len(self.scan_angle), 5)
        ]

        # --- Build substrate and tip ---
        build.tip(self.var)
        build.sub(self.var)

    def system(self):
        """
        Generate LAMMPS input files for the AFM system setup.
        This entails creating the simulation box, reading data files,
        and applying potentials for each layer of the 2D material.

        During the simulations, the system is equilibrated.
        The tip, positioned in the center of the box,
        is indented into the 2D material at various loads.
        Output files are generated as well as visualisation files
        in preperation for sliding simulations.

        """

        for layer in self.var['2D']['layers']:
            tip_x = self.var['dim']['xhi'] / 2
            tip_y = self.var['dim']['yhi'] / 2
            tip_z = 55 + self.var['2D']['lat_c'] * (layer - 1) / 2
            filename = f"{self.directory[layer]}/lammps/system.lmp"

            # --- Find minimum gap between the 2D material and the substrate ---
            gap = potentials.afm(self.var, layer)
            height_2d = 10.5 + gap

            # --- Create the system input file ---
            lammps_lines = [
                f"region box block {self.var['dim']['xlo']} {self.var['dim']['xhi']} {self.var['dim']['ylo']} {self.var['dim']['yhi']} -5 100\n",
                f"create_box      {self.var['ngroups'][layer]} box\n\n",

                "#----------------- Read data files -----------------------\n\n",
                f"read_data       {self.var['dir']}/build/sub.lmp add append group sub\n",
                f"read_data       {self.var['dir']}/build/tip.lmp add append shift {tip_x} {tip_y} {tip_z}  group tip offset {self.var['data']['sub']['natype']} 0 0 0 0\n",
                f"read_data       {self.var['dir']}/build/{self.var['2D']['mat']}_{layer}.lmp add append shift 0.0 0.0 {height_2d} group 2D offset {self.var['data']['tip']['natype']+self.var['data']['sub']['natype']} 0 0 0 0\n\n"

                "# Apply potentials\n\n",
                f"include        {self.directory[layer]}/lammps/system.in.settings\n\n",

                "#----------------- Create visualisation files ------------\n\n",
                f"dump            sys all atom 10000 ./{self.var['dir']}/visuals/system_{layer}.lammpstrj\n\n",

                "#----------------- Minimize the system -------------------\n\n",
                "min_style       cg\n",
                "minimize        1.0e-4 1.0e-8 100 1000\n\n",
                "timestep        0.001\n",
                "thermo          100\n\n",

                "# ----------------- Apply Nose-Hoover thermostat ----------\n\n"
                "group           fixset union sub_fix tip_all\n",
                "group           system subtract all fixset\n\n",
                f"velocity        system create {self.var['general']['temproom']} 492847948\n\n",
                "compute         temp_tip tip_thermo temp/partial 0 1 0\n",
                f"fix             lang_tip tip_thermo langevin {self.var['general']['temproom']} {self.var['general']['temproom']} $(100.0*dt) 699483 zero yes\n",
                "fix_modify      lang_tip temp temp_tip\n\n",
                "compute         temp_sub sub_thermo temp/partial 0 1 0\n",
                f"fix             lang_sub sub_thermo langevin {self.var['general']['temproom']} {self.var['general']['temproom']} $(100.0*dt) 2847563 zero yes\n",
                "fix_modify      lang_sub temp temp_sub\n\n",
                "fix             nve_all all nve\n\n",
                "fix             sub_fix sub_fix setforce 0.0 0.0 0.0 \n",
                "velocity        sub_fix set 0.0 0.0 0.0\n\n",
                "fix             tip_f tip_all rigid/nve single force * off off off torque * off off off\n\n",
                "run             10000\n\n",
                "unfix           tip_f \n\n",
                "##########################################################\n",
                "#--------------------Tip Indentation---------------------#\n",
                "##########################################################\n",
                "#----------------- Displace tip closer -------------------\n\n",
                "displace_atoms  tip_all move 0.0 0.0 -20.0 units box\n\n",
                "#----------------- Apply constraints ---------------------\n\n",

                "fix             tip_f tip_all rigid/nve single force * off off on torque * off off off\n\n",
                "variable        f equal 0.0\n",

                f"variable find index {' '.join(str(x) for x in self.var['general']['force'])}\n",
                "label force_loop\n",

                "#----------------- Set up initial parameters -------------\n\n",
                "variable        num_floads equal 100\n",
                "variable        r equal 0.0\n",
                "variable        fincr equal (${find}-${f})/${num_floads}\n",
                "thermo_modify   lost ignore flush yes\n\n",
                "#----------------- Apply pressure to the tip -------------\n\n",
                "variable i loop ${num_floads}\n",
                "label loop_load\n\n",
                "variable f equal ${f}+${fincr} \n\n",
                "# Set force variable\n\n",
                "variable Fatom equal -v_f/(count(tip_fix)*1.602176565)\n",
                "fix forcetip tip_fix aveforce 0.0 0.0 ${Fatom}\n",
                "run 100 \n\n",
                "unfix forcetip\n\n",
                "next i\n",
                "jump SELF loop_load\n\n",
                "##########################################################\n",
                "#---------------------Equilibration----------------------#\n",
                "##########################################################\n\n",
                "fix forcetip tip_fix aveforce 0.0 0.0 ${Fatom}\n",
                "variable        dispz equal xcm(tip_fix,z)\n\n",
                "run 100 pre yes post no\n\n",
                "# Prepare to loop for displacement checks\n\n",
                "label check_r\n\n",
                "variable disp_l equal ${dispz}\n",
                "variable disp_h equal ${dispz}\n\n",
                "variable disploop loop 50\n",
                "label disp\n\n",
                "run 100 pre no post no\n\n",
                "if '${dispz}>${disp_h}' then 'variable disp_h equal ${dispz}'\n",
                "if '${dispz}<${disp_l}' then 'variable disp_l equal ${dispz}'\n\n",
                "next disploop\n",
                "jump SELF disp\n\n",
                "variable r equal ${disp_h}-${disp_l}\n\n",
                "# Check if r is less than 0.1\n\n",
                "if '${r} < 0.2' then 'jump SELF loop_end' else 'jump SELF check_r'\n\n",
                "# End of the loop\n\n",
                "label loop_end\n\n",
                f"write_data {self.directory[layer]}/data/load_$(v_find)N.data\n",
                "next find\n",
                "jump SELF force_loop"
            ]

            with open(filename, 'w', encoding="utf-8") as f:
                settings.file.init(f)
                f.write(lammps_lines)

    def slide(self):
        """
        Generate LAMMPS input files for the AFM sliding setup.
        This reads the output file generated during the indentation
        and applies lateral motion to the tip while maintaining the 
        normal load to generate friction. 

        Output data is collected in a .txt file. 

        """
        # 1.602176565 nN = 1 eV/Angstrom
        # 1 Angstrom = 10^(-10) m
        # 1 ps = 10^ (-12) s

        # Convert spring constant to eV/A^2
        spring_ev = self.var['tip']['cspring'] / 16.02176565
        # Spring Damper to eV/(A^2/ps)
        damp_ev = self.var['tip']['dspring'] / 0.01602176565
        # Tip speed to Angstrom/ps
        tipps = self.var['tip']['s']/100

        for layer in self.var['2D']['layers']:

            filename = f"{self.directory[layer]}/lammps/slide_{self.var['tip']['s']}ms.lmp"
            with open(filename, 'w', encoding="utf-8") as f:
                f.writelines([
                    f"variable find index {' '.join(str(x) for x in self.var['general']['force'])}\n",
                    "label force_loop\n",

                    f"variable a index 0 {' '.join(str(x) for x in self.scan_angle)} 0\n",
                    "label angle_loop\n",
                ])
                settings.file.init(f)

                f.writelines([
                    f"read_data       {self.directory[layer]}/data/load_$(v_find)N.data # Read system data\n\n",
                    f"include         {self.directory[layer]}/lammps/system.in.settings\n\n",

                    "#----------------- Create visualisation files ------------\n\n",
                    f"dump            sys all atom 10000 ./{self.var['dir']}/visuals/slide_{self.var['tip']['s']}ms_l{layer}.lammpstrj\n\n"
                    "dump_modify sys append yes\n",
                    "##########################################################\n",
                    "#--------------------Tip Indentation---------------------#\n",
                    "##########################################################\n",
                    "#----------------- Apply constraints ---------------------\n\n",

                    "fix             sub_fix sub_fix setforce 0.0 0.0 0.0 \n",
                    "fix             tip_f tip_all rigid/nve single force * on on on torque * off off off\n\n",

                    "#----------------- Apply Langevin thermostat -------------\n\n",
                    "compute         temp_tip tip_thermo temp/partial 0 1 0\n",
                    f"fix             lang_tip tip_thermo langevin {self.var['general']['temproom']} {self.var['general']['temproom']} $(100.0*dt) 699483 zero yes\n",
                    "fix_modify      lang_tip temp temp_tip\n\n",
                    "compute         temp_base sub_thermo temp/partial 0 1 0\n",
                    f"fix             lang_bot sub_thermo langevin {self.var['general']['temproom']} {self.var['general']['temproom']} $(100.0*dt) 2847563 zero yes\n",
                    "fix_modify      lang_bot temp temp_base\n\n",
                    "fix             nve_all all nve\n",

                    "timestep        0.001\n",
                    "thermo          100\n\n",

                    "#----------------- Apply pressure to the tip -------------\n\n",
                    "variable        Ftotal          equal -v_find/1.602176565\n",
                    "variable        Fatom           equal v_Ftotal/count(tip_fix)\n",
                    "fix             forcetip tip_fix aveforce 0.0 0.0 ${Fatom}\n\n",

                    "##########################################################\n",
                    "#------------------------Compute-------------------------#\n",
                    "##########################################################\n\n",

                    f"compute COM_top layer_{layer} com\n",
                    "variable comx equal c_COM_top[1] \n",
                    "variable comy equal c_COM_top[2] \n",
                    "variable comz equal c_COM_top[3] \n\n",

                    "compute COM_tip tip_fix com\n",
                    "variable comx_tip equal c_COM_tip[1] \n",
                    "variable comy_tip equal c_COM_tip[2] \n",
                    "variable comz_tip equal c_COM_tip[3] \n\n",
                    "#----------------- Calculate total friction --------------\n\n",
                    "variable        fz_tip   equal  f_forcetip[3]*1.602176565\n\n",
                    "variable        fx_spr   equal  f_spr[1]*1.602176565\n\n",
                    "variable        fy_spr   equal f_spr[2]*1.602176565\n\n",
                    f"fix             fc_ave all ave/time 1 1000 1000 v_fz_tip v_fx_spr v_fy_spr v_comx v_comy v_comz v_comx_tip v_comy_tip v_comz_tip file ./{self.var['dir']}/results/fc_ave_slide_$(v_find)nN_$(v_a)angle_{self.var['tip']['s']}ms_l{layer}\n\n",

                    "##########################################################\n",
                    "#---------------------Spring Loading---------------------#\n",
                    "##########################################################\n\n",
                    "#----------------- Add damping force ---------------------\n\n",
                    f"fix             damp tip_fix viscous {damp_ev}\n\n",

                    "variable spring_x equal cos(v_a*PI/180)\n",
                    "variable spring_y equal sin(v_a*PI/180)\n\n",
                    "#------------------Add lateral harmonic spring------------\n\n",
                    f"fix             spr tip_fix smd cvel {spring_ev} {tipps} tether $(v_spring_x) $(v_spring_y) NULL 0.0\n\n",
                    "run 100000\n\n",

                    f"if '$(v_a) == {self.var['general']['scan_angle'][3]}' then &\n",
                    "'next a' & \n",
                    "'jump SELF find_incr'\n\n",

                    f"if '$(v_find) == {self.var['general']['scan_angle'][3]}' then &\n",
                    "'next a' & \n",
                    "'clear' & \n",
                    "'jump SELF angle_loop'\n\n",

                    "label find_incr\n\n",
                    "next find\n",
                    "clear\n",
                    "jump SELF force_loop"
                ])
