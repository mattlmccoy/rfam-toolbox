# Installation Guide

Step-by-step instructions for installing RFAM Toolbox on every supported platform.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | >= 3.9 | [Download](https://www.python.org/downloads/) |
| pip | any recent | Bundled with Python |
| tkinter | — | Usually bundled with Python (see below) |

---

## Linux

### Ubuntu / Debian

```bash
# 1. Install Python and tkinter
sudo apt-get update
sudo apt-get install python3 python3-pip python3-tk

# 2. Install RFAM Toolbox
pip install rfam-toolbox

# 3. Verify
rfam-toolbox --version
```

### Fedora / RHEL / CentOS

```bash
# 1. Install Python and tkinter
sudo dnf install python3 python3-pip python3-tkinter

# 2. Install RFAM Toolbox
pip install rfam-toolbox

# 3. Verify
rfam-toolbox --version
```

### Arch Linux

```bash
# 1. Install Python and tk
sudo pacman -S python python-pip tk

# 2. Install RFAM Toolbox
pip install rfam-toolbox

# 3. Verify
rfam-toolbox --version
```

### Using the install script

```bash
bash scripts/install.sh
```

This script auto-detects your distribution and checks all prerequisites.

---

## macOS

Works on both Apple Silicon (M1/M2/M3/M4) and Intel Macs.

### With Homebrew (recommended)

```bash
# 1. Install Python (includes pip)
brew install python

# 2. Install tkinter
brew install python-tk

# 3. Install RFAM Toolbox
pip3 install rfam-toolbox

# 4. Verify
rfam-toolbox --version
```

### With python.org installer

1. Download Python 3.9+ from [python.org](https://www.python.org/downloads/macos/)
2. Run the installer (tkinter is included)
3. Open Terminal and run:

```bash
pip3 install rfam-toolbox
rfam-toolbox --version
```

### Using the install script

```bash
bash scripts/install.sh
```

---

## Windows

### With python.org installer (recommended)

1. Download Python 3.9+ from [python.org](https://www.python.org/downloads/windows/)
2. **During installation, check these boxes:**
   - "Add Python to PATH"
   - "tcl/tk and IDLE" (under Optional Features)
3. Open PowerShell or Command Prompt and run:

```powershell
pip install rfam-toolbox
rfam-toolbox --version
```

### With winget

```powershell
# 1. Install Python
winget install Python.Python.3.12

# 2. Restart your terminal, then:
pip install rfam-toolbox
rfam-toolbox --version
```

### Using the install script

```powershell
.\scripts\install.ps1
```

---

## Installing from Source

If you want to run the latest code or contribute to development:

```bash
git clone https://github.com/mattlmccoy/rfam-toolbox.git
cd rfam-toolbox
pip install -e ".[dev]"
```

The `-e` flag installs in "editable" mode so changes take effect immediately.

---

## Optional: PDF Support

To import scanned PDFs directly, you need poppler (a system library) plus the Python wrapper.

### Install poppler

| Platform | Command |
|----------|---------|
| macOS | `brew install poppler` |
| Ubuntu / Debian | `sudo apt-get install poppler-utils` |
| Fedora | `sudo dnf install poppler-utils` |
| Arch | `sudo pacman -S poppler` |
| Windows | Download from [osber/pdf2image](https://github.com/osber/pdf2image) and add to PATH |

### Install the Python wrapper

```bash
pip install rfam-toolbox[pdf]
```

---

## Troubleshooting

### "command not found: rfam-toolbox"

pip may have installed the script to a directory not on your PATH.

**Fix:**
```bash
# Find where pip installed it
python -m site --user-base
# Add that directory's bin/ (Linux/macOS) or Scripts/ (Windows) to your PATH

# Or run directly:
python -m rfam_toolbox
```

### "No module named tkinter"

tkinter is not bundled on some Linux distributions.

**Fix:** Install it with your package manager (see platform sections above).

### "ModuleNotFoundError: No module named cv2"

OpenCV failed to install. This occasionally happens with very new Python versions.

**Fix:**
```bash
pip install --upgrade pip
pip install opencv-python
```

### Permission errors during install

**Fix:** Use `--user` to install for your user only:
```bash
pip install --user rfam-toolbox
```

Or use a virtual environment (recommended):
```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows
pip install rfam-toolbox
```

### macOS: "This app is damaged" or security warnings

macOS may block unsigned applications. Since RFAM Toolbox runs from Python directly, this shouldn't happen. If it does, ensure you're launching via the terminal:
```bash
rfam-toolbox
```

---

## Verifying Your Installation

After installing, run these checks:

```bash
# Check version
rfam-toolbox --version

# Check imports
python -c "import rfam_toolbox; print('OK')"

# Launch the tool
rfam-toolbox
```
