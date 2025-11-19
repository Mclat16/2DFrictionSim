"""Base builder class for FrictionSim2D simulations.

This module defines the abstract base class for all simulation builders.
It handles common tasks such as directory creation, configuration loading,
Atomsk wrapper initialization, and Jinja2 template rendering.
"""
from importlib import resources
import logging
from pathlib import Path
from typing import Optional, Any, Dict, List
from abc import ABC, abstractmethod

import jinja2

from FrictionSim2D.core.config import GlobalSettings, AFMSimulationConfig, SheetOnSheetSimulationConfig
from FrictionSim2D.interfaces.atomsk import AtomskWrapper
from FrictionSim2D.core.utils import get_potential_path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BaseBuilder(ABC):
    """Abstract base class for simulation builders.

    Attributes:
        config (AFMSimulationConfig): The validated configuration object.
        settings (GlobalSettings): The global software settings.
        atomsk (AtomskWrapper): The wrapper for the Atomsk binary.
        work_dir (Path): The root directory for the current simulation output.
    """

    def __init__(self, config: AFMSimulationConfig, output_dir: Optional[Path] = None):
        """Initialize the BaseBuilder.

        Args:
            config (AFMSimulationConfig): Validated configuration object.
            output_dir (Optional[Path]): Root directory for output. If None,
                defaults to the current working directory.
        """
        self.config = config
        self.settings = config.settings
        
        # Initialize Atomsk Wrapper
        self.atomsk = AtomskWrapper()

        # Setup Output Directory
        self.work_dir = output_dir if output_dir else Path.cwd()
        
        # Setup Jinja2 Template Environment
        # We point the loader to the 'templates' directory inside the package
        template_dir = resources.files('FrictionSim2D.templates')
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(template_dir)),
            trim_blocks=True,
            lstrip_blocks=True
        )

    def setup_directories(self, subdirs: list[str]) -> None:
        """Creates the simulation directory structure.

        Args:
            subdirs (list[str]): List of subdirectory names to create 
                                (e.g., ['visuals', 'results']).
        """
        for subdir in subdirs:
            path = self.work_dir / subdir
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.error(f"Failed to create directory {path}: {e}")
                raise

    def render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """Renders a Jinja2 template with the provided context.

        Args:
            template_name (str): Relative path to the template (e.g., 'afm/slide.lmp').
            context (Dict[str, Any]): Dictionary of variables to pass to the template.

        Returns:
            str: The rendered content.
        """
        try:
            template = self.jinja_env.get_template(template_name)
            return template.render(context)
        except jinja2.TemplateError as e:
            logger.error(f"Failed to render template '{template_name}': {e}")
            raise

    def _generate_potential_commands(self) -> List[str]:
        """Generates the LAMMPS commands for setting up potentials."""
        commands = []
        unique_potentials = {}
        
        # Consolidate components from the specific config
        components_to_process = {}
        if isinstance(self.config, AFMSimulationConfig):
            components_to_process = {
                'tip': self.config.tip,
                'sub': self.config.sub,
                'sheet': self.config.sheet
            }
        elif isinstance(self.config, SheetOnSheetSimulationConfig):
            components_to_process = {
                'sheet1': self.config.sheet1,
                'sheet2': self.config.sheet2
            }

        for component_name, component_config in components_to_process.items():
            # Resolve the potential path using the helper
            pot_path = get_potential_path(str(component_config.pot_path))
            
            if str(pot_path) not in unique_potentials:
                unique_potentials[str(pot_path)] = {
                    "type": component_config.pot_type,
                    "components": []
                }
            unique_potentials[str(pot_path)]["components"].append(component_name)

        # Create pair_style and pair_coeff commands
        pair_style_parts = []
        pair_coeff_commands = []
        
        for path, info in unique_potentials.items():
            pair_style_parts.append(info['type'])
        
        if pair_style_parts:
            commands.append(f"pair_style hybrid {' '.join(pair_style_parts)}")
            
            for path, info in unique_potentials.items():
                # This part might need adjustment based on how atom types are mapped
                # Assuming a simple mapping for now
                pair_coeff_commands.append(f"pair_coeff * * {info['type']} {path} ...") # Placeholder

        # This is a simplified placeholder. The actual implementation will need to
        # correctly map atom types to pair_coeff commands, which is complex.
        # For now, we'll just show the resolved paths.
        logging.info("--- Resolved Potentials ---")
        for path, info in unique_potentials.items():
            logging.info("  Path: %s", path)
            logging.info("  Type: %s", info['type'])
            logging.info("  Used by: %s", info['components'])
        logging.info("--------------------------")
        # This is a placeholder for the actual commands
        # commands.extend(pair_coeff_commands)

        return commands

    @abstractmethod
    def build(self) -> None:
        """Main execution method to build the simulation.
        
        Must be implemented by child classes (e.g., AFMSimulation).
        """
        pass

    @abstractmethod
    def write_inputs(self) -> None:
        """Writes the LAMMPS input scripts.
        
        Must be implemented by child classes.
        """
        pass