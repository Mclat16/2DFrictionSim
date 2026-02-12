# Provenance Architecture

## Overview

The provenance system tracks reproducibility of simulations by recording all input files (CIFs, potentials, configs) with component-level metadata. This enables:

1. **No duplication of large potential files** (symlinks)
2. **Component traceability** (which potential for tip? which CIF for substrate?)
3. **AiiDA integration** (manifest readable during workflow)

## How It Works

### 1. Simulation Setup (`SimulationBase.add_to_provenance()`)

When building a simulation, call:
```python
sim = AFMSimulation(config, output_dir)
sim.add_to_provenance('/path/to/potentials/Au.sw', category='potential', component='tip')
sim.add_to_provenance('/path/to/cif/MoS2.cif', category='cif', component='substrate')
```

**File Handling:**
- **Potentials**: Creates a symlink (no duplication)
- **CIFs**: Copies the file (small, component-specific)
- **Config files**: Copied during `init_provenance()`

**Result:**
```
output_dir/
├── provenance/
│   ├── manifest.json          # Component-to-file mapping
│   ├── config.ini             # Copy of config
│   ├── materials_list.txt     # Copy of materials
│   ├── cif/
│   │   └── MoS2.cif           # Copy
│   └── potentials/
│       └── Au.sw              # Symlink → /repo/potentials/Au.sw
```

### 2. Provenance Manifest

The `manifest.json` file tracks component usage:

```json
{
  "version": "1.0",
  "created": "2025-01-19T14:30:00",
  "last_updated": "2025-01-19T14:35:00",
  "files": [
    {
      "filename": "Au.sw",
      "original_path": "/home/user/repo/potentials/Au.sw",
      "stored_path": "provenance/potentials/Au.sw",
      "category": "potential",
      "component": "tip",
      "checksum": "abc123...",
      "added_at": "2025-01-19T14:30:30"
    },
    {
      "filename": "MoS2.cif",
      "original_path": "/home/user/repo/structures/MoS2.cif",
      "stored_path": "provenance/cif/MoS2.cif",
      "category": "cif",
      "components": ["substrate"],
      "checksum": "def456...",
      "added_at": "2025-01-19T14:30:45"
    }
  ]
}
```

**Key features:**
- Maps each file to its component usage
- Records original path (for validation/debugging)
- Includes checksums for integrity verification
- Timestamp for audit trail

### 3. AiiDA Integration (`FrictionProvenanceData.from_provenance_folder()`)

When creating AiiDA provenance nodes:

```python
from src.aiida.data.provenance import FrictionProvenanceData

prov_node = FrictionProvenanceData.from_provenance_folder(
    provenance_dir / 'provenance',
    simulation_type='afm'
)
```

**What happens:**
1. Reads `manifest.json` and stores component mappings
2. Stores all files in AiiDA repository (potentials as symlinks)
3. Makes the mapping available via:
   ```python
   prov_node.file_manifest  # dict mapping components to files
   ```

**Example usage in workflows:**
```python
manifest = prov_node.file_manifest
tip_potential = manifest.get('tip', {}).get('potential')
substrate_cif = manifest.get('substrate', {}).get('cif')

# Create component-specific input nodes
tip_pot_node = load_potential(tip_potential)
substrate_node = load_cif(substrate_cif)
```

## Directory Structure in Provenance

```
provenance/
├── manifest.json                    # Maps components to files
├── config.ini                       # Simulation config (copy)
├── settings.yaml                    # Optional settings (copy)
├── materials_list.txt               # Optional materials list (copy)
├── cif/
│   ├── substrate.cif               # CIF files (copies)
│   └── coating.cif
└── potentials/
    ├── Au.sw                       # Potential files (SYMLINKS)
    ├── W.sw
    └── MoS2.sw
```

## Benefits

| Issue | Solution |
|-------|----------|
| Large potentials duplicated | Use symlinks - stored as references |
| Can't trace tip potential to tip | Manifest tracks component→file mapping |
| AiiDA can't find component origins | Read manifest during node creation |
| Manual tracing of provenance | Checksums + timestamps for audit |

## Backward Compatibility

The manifest is optional:
- If missing, the system still works (just no component metadata)
- Old provenance folders without manifest can still be loaded
- New code auto-generates manifest on `add_to_provenance()` calls