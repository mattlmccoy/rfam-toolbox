# BJAM Toolbox

[![CI](https://github.com/mattlmccoy/rfam-toolbox/actions/workflows/ci.yml/badge.svg)](https://github.com/mattlmccoy/rfam-toolbox/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/bjam-toolbox.svg)](https://pypi.org/project/bjam-toolbox/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Open-source tools for Binder Jet Additive Manufacturing (BJAM) process development.**

This repository provides two complementary analysis tools designed to help researchers and operators assess and improve print quality:

1. **Dimensional Accuracy Tool** - Measure placement accuracy, feature size, and shape fidelity of printed calibration patterns
2. **Ink Concentration Tool** - Analyze ink deposition properties through region-of-interest measurements

Both tools use high-resolution flatbed scanners as the primary imaging device, providing micron-scale measurement capability at commodity cost.

---

## Installation

### Quick Install (all platforms)

```bash
pip install bjam-toolbox
```

### From Source

```bash
git clone https://github.com/mattlmccoy/rfam-toolbox.git
cd rfam-toolbox
pip install .
```

### Using the Install Scripts

**Linux / macOS:**
```bash
bash scripts/install.sh
```

**Windows (PowerShell):**
```powershell
.\scripts\install.ps1
```

The install scripts check for Python 3.9+, tkinter, and install the package automatically.

### Prerequisites

- **Python 3.9 or higher** ([download](https://www.python.org/downloads/))
- **tkinter** (usually bundled with Python)

If tkinter is missing:

| Platform | Command |
|----------|---------|
| macOS | `brew install python-tk` |
| Ubuntu / Debian | `sudo apt-get install python3-tk` |
| Fedora / RHEL | `sudo dnf install python3-tkinter` |
| Windows | Reinstall Python and check "tcl/tk and IDLE" |

### Optional: PDF Support

To import scanned PDFs directly, install poppler:

```bash
# macOS
brew install poppler

# Ubuntu/Debian
sudo apt-get install poppler-utils

# Windows — download from https://github.com/osber/pdf2image
```

Then install the PDF extra: `pip install bjam-toolbox[pdf]`

For detailed platform-specific instructions, see [INSTALL.md](INSTALL.md).

---

## Quick Start

### Launch the tool

```bash
bjam-toolbox
```

Or equivalently:

```bash
python -m bjam_toolbox
```

A dialog will ask which workflow you want to use:
- **Yes** → Dimensional Accuracy Analysis
- **No** → Ink Concentration Analysis

### Verify Installation

```bash
bjam-toolbox --version
```

---

## Features

### Dimensional Accuracy Analysis
- Analyze four calibration feature types:
  - **Dot arrays**: Measure placement accuracy, dot diameter, circularity, and eccentricity
  - **Checkerboards**: Extract rotation (yaw) and scale with edge-based detection
  - **Concentric rings**: Stress-test edge fidelity and linewidth consistency
  - **Pitch rulers**: Characterize minimum resolvable feature size
- Generate compensation recommendations (scale factors, rotation corrections)
- Produce health indicators that flag when process tuning is needed
- Export standardized CSV data products for tracking calibration over time

### Ink Concentration Analysis
- Interactive region-of-interest (ROI) selection with polygon, circle, and ruler tools
- Compute intensity metrics (mean, median, std, IQR, skewness, kurtosis, entropy)
- Compute shape metrics (circularity, perimeter, convexity, inertia ratio)
- Halo/spreading analysis via eccentricity measurements
- Generate statistical plots and heatmaps

---

## Workflows

### Dimensional Accuracy Workflow

1. **Select image**: Load a scanned calibration pattern (PNG, JPG, TIF, or PDF)
2. **Enter scanner DPI**: The tool calculates pixel-to-mm conversion automatically
3. **Enter metadata**: Sample ID, ink type, feathering percentage, gantry speed
4. **Select features**: Check which features to analyze (dots, checkerboard, rings, pitch rulers)
5. **Draw ROIs**: For each feature, draw a bounding box around the region to analyze
6. **Review results**: The tool generates:
   - `results.csv`: Summary metrics
   - `raw.csv`: Per-instance measurements
   - Debug overlay images
   - Dimensional health report with compensation recommendations

### Ink Concentration Workflow

1. **Select image**: Load a scanned ink deposition sample
2. **Draw ROIs**: Use keyboard shortcuts to draw regions:
   - `P`: Polygon mode (click vertices, right-click to close)
   - `C`: Circle mode (hold and drag)
   - `L`: Ruler mode (calibrate pixel-to-mm scale)
3. **Label ROIs**: Press `1-4` to assign ink type labels
4. **Toggle metrics**: Press `I/S/H` for intensity/shape/halo analysis
5. **Generate results**: Press `Q` to finish and export

---

## Repository Structure

```
rfam-toolbox/
├── bjam_toolbox/              # Main package
│   ├── __main__.py            # python -m bjam_toolbox entry point
│   ├── launcher.py            # Unified entry point
│   ├── dimensional/           # Dimensional accuracy analysis
│   │   ├── gui.py             # GUI for dimensional workflow
│   │   ├── analysis.py        # Feature analysis algorithms
│   │   └── geometry.py        # Test pattern generation
│   ├── ink_concentration/     # Ink analysis
│   │   ├── main.py            # Workflow orchestration
│   │   ├── gui.py             # ROI selection interface
│   │   ├── analyzer.py        # Metric computation
│   │   └── plots.py           # Visualization
│   └── common/                # Shared utilities
│       ├── dataio.py          # CSV export
│       └── utils.py           # Helper functions
├── geometries/                # Reference calibration patterns
│   └── gold_standard_patterns/
├── scripts/                   # Install helper scripts
│   ├── install.sh             # Linux / macOS installer
│   └── install.ps1            # Windows installer
├── .github/workflows/         # CI/CD
│   ├── ci.yml                 # Test matrix (Linux, macOS, Windows)
│   └── publish.yml            # Auto-publish to PyPI on release
├── pyproject.toml             # Package configuration
├── requirements.txt
├── Makefile
├── LICENSE
├── README.md
├── INSTALL.md                 # Detailed platform install guide
└── CONTRIBUTING.md            # Developer guide
```

---

## Output Data Products

Each analysis run creates a timestamped folder under `session_data/` containing:

| File | Description |
|------|-------------|
| `results.csv` | Summary metrics (one row per feature type) |
| `raw.csv` | Per-instance measurements (e.g., each dot's diameter) |
| `dimensional_summary.txt` | Human-readable summary |
| `dimensional_compensation.txt` | Recommended calibration adjustments |
| `*_overlay.png` | Visualization of detected features |
| `*_roi.png` | Cropped region of interest |
| `source_image.png` | Copy of input image |

---

## Calibration Pattern Design

The tool is designed to work with calibration patterns containing:

- **Dot array**: 5x5 grid of 2mm diameter dots at 6mm pitch
- **Checkerboard**: 8x8 pattern of 2mm squares
- **Concentric rings**: 20 rings with 0.5mm line width and 0.5mm spacing
- **Pitch rulers**: Bars with widths from 0.1mm to 6mm

You can generate custom patterns using:
```python
from bjam_toolbox.dimensional.geometry import generate_pattern
generate_pattern(dpi=4800, output_path="my_pattern.png")
```

Pre-generated gold standard patterns at various DPI values are included in `geometries/gold_standard_patterns/`.

---

## Understanding the Health Report

The dimensional health report separates two types of outputs:

### Compensation Recommendations
- **Scale factors**: Multiply X/Y coordinates to correct placement errors
- **Rotation correction**: Angular adjustment to correct yaw misalignment
- These correct motion-system calibration issues

### Health Indicators
- **Normalized circularity**: Values below ~0.9 indicate spreading/coalescence
- **Eccentricity**: Non-zero values indicate directional stretching
- **Ring variability**: High values indicate edge quality issues
- These flag when process tuning (not calibration) is needed

---

## Citation

If you use this tool in your research, please cite:

```bibtex
@article{mccoy2025scanner,
  title={A Low-Cost Scanner-Based Diagnostic Pipeline for Dimensional Metrology
         of Jetting Fidelity in Binder Jet Additive Manufacturing},
  author={McCoy, Matthew L. and Salda{\~n}a, Christopher J. and Seepersad, Carolyn C.},
  journal={Additive Manufacturing},
  year={2025}
}
```

---

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

This work was supported by the National Science Foundation under Grant No. DGE-2039655.

## Contact

Matthew L. McCoy - matthew.mccoy@gatech.edu

George W. Woodruff School of Mechanical Engineering
Georgia Institute of Technology
