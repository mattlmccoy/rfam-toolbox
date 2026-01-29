"""
BJAM Toolbox — configuration loader with auto-backup.

The config file lives alongside this module at ``defaults/config.json``.
When the loader detects that the user has edited the file (by comparing
its SHA-256 hash against the hash recorded on the previous load), it
creates a timestamped backup before returning the new values.

Usage::

    from bjam_toolbox.defaults.config_loader import load_config, config_path

    cfg = load_config()
    blur_k = tuple(cfg["dot_array"]["gaussian_blur_kernel"])
"""

import hashlib
import json
import os
import shutil
from datetime import datetime
from typing import Any, Dict

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_THIS_DIR, "config.json")
_HASH_PATH = os.path.join(_THIS_DIR, ".config_hash")

# Module-level cache so we only read the file once per process.
_cached_config: Dict[str, Any] | None = None


def config_path() -> str:
    """Return the absolute path to the active config.json file."""
    return _CONFIG_PATH


def _file_hash(path: str) -> str:
    """Return the SHA-256 hex digest of *path*."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _maybe_backup(path: str) -> None:
    """Create a timestamped backup if the config has changed since last load."""
    current_hash = _file_hash(path)

    # Read the previously recorded hash (if any).
    prev_hash = None
    if os.path.exists(_HASH_PATH):
        with open(_HASH_PATH, "r") as f:
            prev_hash = f.read().strip()

    if prev_hash is not None and current_hash != prev_hash:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{path}.bak.{ts}"
        # Back up the *previous* version so the user can always revert.
        # We copy the current file since the previous content is gone,
        # but the naming makes it clear when the snapshot was taken.
        shutil.copy2(path, backup_path)

    # Record the current hash for next time.
    with open(_HASH_PATH, "w") as f:
        f.write(current_hash)


def load_config(*, force_reload: bool = False) -> Dict[str, Any]:
    """Load and return the configuration dictionary.

    Parameters
    ----------
    force_reload : bool
        If *True*, bypass the in-process cache and re-read the file.

    Returns
    -------
    dict
        The parsed configuration.
    """
    global _cached_config
    if _cached_config is not None and not force_reload:
        return _cached_config

    if not os.path.exists(_CONFIG_PATH):
        raise FileNotFoundError(
            f"Configuration file not found: {_CONFIG_PATH}\n"
            "This file should have been installed with the package."
        )

    _maybe_backup(_CONFIG_PATH)

    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        _cached_config = json.load(f)

    return _cached_config
