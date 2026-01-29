# Contributing to BJAM Toolbox

Contributions are welcome! This guide covers how to set up the project for development and submit changes.

---

## Development Setup

```bash
# 1. Fork and clone the repository
git clone https://github.com/<your-username>/rfam-toolbox.git
cd rfam-toolbox

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

# 3. Install in editable mode with dev dependencies
pip install -e ".[dev,pdf]"

# Or use the Makefile shortcut:
make dev
```

---

## Project Structure

- `bjam_toolbox/` — main package source code
- `bjam_toolbox/dimensional/` — dimensional accuracy analysis module
- `bjam_toolbox/ink_concentration/` — ink concentration analysis module
- `bjam_toolbox/common/` — shared utilities
- `geometries/` — reference calibration patterns
- `scripts/` — install helper scripts
- `tests/` — unit tests

---

## Code Style

- **Formatter**: [Black](https://github.com/psf/black) (line length 120)
- **Linter**: [Flake8](https://flake8.pycqa.org/) (line length 120)

```bash
# Format code
make format

# Check linting
make lint
```

---

## Running Tests

```bash
make test
# or
pytest tests/ -v
```

---

## Submitting Changes

1. Create a feature branch from `main`:
   ```bash
   git checkout -b feature/your-feature
   ```

2. Make your changes and ensure they pass linting:
   ```bash
   make lint
   ```

3. Commit with a clear message:
   ```bash
   git commit -m "Add description of what changed and why"
   ```

4. Push to your fork:
   ```bash
   git push origin feature/your-feature
   ```

5. Open a Pull Request against the `main` branch.

---

## Release Process (maintainers)

1. Update the version in `bjam_toolbox/__init__.py` and `pyproject.toml`
2. Commit the version bump
3. Create a GitHub Release with a tag like `v1.0.1`
4. The `publish.yml` workflow will automatically build and push to PyPI
