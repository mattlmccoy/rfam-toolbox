#!/usr/bin/env bash
# BJAM Toolbox — cross-platform installer for Linux and macOS.
# Usage:  curl -sSL https://raw.githubusercontent.com/mattlmccoy/rfam-toolbox/main/scripts/install.sh | bash
#   or:   bash scripts/install.sh          (from a local checkout)
set -euo pipefail

MIN_PYTHON="3.9"
PACKAGE="bjam-toolbox"

# ---------- helpers ----------------------------------------------------------
info()  { printf '\033[1;34m[info]\033[0m  %s\n' "$*"; }
ok()    { printf '\033[1;32m[ok]\033[0m    %s\n' "$*"; }
warn()  { printf '\033[1;33m[warn]\033[0m  %s\n' "$*"; }
fail()  { printf '\033[1;31m[error]\033[0m %s\n' "$*"; exit 1; }

# ---------- detect Python ----------------------------------------------------
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done
[ -n "$PYTHON" ] || fail "Python not found. Please install Python ${MIN_PYTHON}+ first."

PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Found $PYTHON ($PY_VERSION)"

# Check version
"$PYTHON" -c "
import sys
min_ver = tuple(int(x) for x in '${MIN_PYTHON}'.split('.'))
if sys.version_info[:2] < min_ver:
    print(f'Python {sys.version_info.major}.{sys.version_info.minor} is too old (need >= ${MIN_PYTHON})')
    sys.exit(1)
" || fail "Python >= ${MIN_PYTHON} required (found ${PY_VERSION})."

# ---------- detect OS & check tkinter ----------------------------------------
OS="$(uname -s)"

check_tkinter() {
    "$PYTHON" -c "import tkinter" 2>/dev/null
}

install_tkinter_hint() {
    case "$OS" in
        Linux)
            if command -v apt-get &>/dev/null; then
                warn "tkinter not found. Install it with:"
                warn "  sudo apt-get install python3-tk"
            elif command -v dnf &>/dev/null; then
                warn "tkinter not found. Install it with:"
                warn "  sudo dnf install python3-tkinter"
            elif command -v pacman &>/dev/null; then
                warn "tkinter not found. Install it with:"
                warn "  sudo pacman -S tk"
            else
                warn "tkinter not found. Install the python3-tk package for your distribution."
            fi
            ;;
        Darwin)
            warn "tkinter not found. Install it with:"
            warn "  brew install python-tk"
            ;;
        *)
            warn "tkinter not found. Please install it for your platform."
            ;;
    esac
}

if ! check_tkinter; then
    install_tkinter_hint
    fail "tkinter is required but not installed. See the message above."
fi
ok "tkinter is available"

# ---------- install the package ----------------------------------------------
info "Installing ${PACKAGE} ..."

# If we're inside a local checkout, install from it; otherwise install from PyPI.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/../pyproject.toml" ]; then
    info "Local checkout detected — installing from source."
    "$PYTHON" -m pip install "${SCRIPT_DIR}/.." --quiet
else
    "$PYTHON" -m pip install "$PACKAGE" --quiet
fi

# ---------- verify -----------------------------------------------------------
if command -v bjam-toolbox &>/dev/null; then
    VERSION=$(bjam-toolbox --version)
    ok "Installation complete: ${VERSION}"
else
    # Entry-point script may not be on PATH if --user install
    ok "Installation complete. If 'bjam-toolbox' is not found, add"
    ok "  $("$PYTHON" -m site --user-base)/bin to your PATH."
fi

info "Run 'bjam-toolbox' to launch the application."
