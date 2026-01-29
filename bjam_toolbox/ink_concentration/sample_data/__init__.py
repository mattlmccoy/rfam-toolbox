"""
sample_data — Bundled CSV datasets for BJAM ink concentration analysis.

Usage
-----
>>> from bjam_toolbox.ink_concentration.sample_data import get_path
>>> training_csv = get_path("chroma_training_data.csv")
>>> test_csv     = get_path("test_bayesian_3class.csv")

Available files
---------------
- ``chroma_training_data.csv``  — 175 chroma paper samples (63× 5wt% petro,
  35× 25wt% petro, 77× 25wt% IPA).  Use as **training data** for all
  classification and estimation modes.

- ``test_bayesian_3class.csv``  — 15 hold-out samples (5 per class).
  Use as **session data** for Bayesian Classification.

- ``test_5petro_25IPA.csv``     — 10 hold-out samples (5× 5wt% petro +
  5× 25wt% IPA).  Use as session data for Bayesian or standard Classification.

- ``test_concentration.csv``    — 6 petroleum-only samples (3× 5wt% + 3× 25wt%).
  Use as session data for Concentration Estimation.
"""

from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent


def get_path(filename: str) -> str:
    """Return the absolute path to a bundled sample-data CSV.

    Parameters
    ----------
    filename : str
        One of the CSV filenames listed in the module docstring.

    Returns
    -------
    str
        Absolute filesystem path to the file.

    Raises
    ------
    FileNotFoundError
        If *filename* does not exist in the sample_data directory.
    """
    path = _DATA_DIR / filename
    if not path.exists():
        available = sorted(p.name for p in _DATA_DIR.glob("*.csv"))
        raise FileNotFoundError(
            f"{filename!r} not found in sample_data.  "
            f"Available files: {available}"
        )
    return str(path)


def list_files() -> list[str]:
    """Return a sorted list of all bundled CSV filenames."""
    return sorted(p.name for p in _DATA_DIR.glob("*.csv"))
