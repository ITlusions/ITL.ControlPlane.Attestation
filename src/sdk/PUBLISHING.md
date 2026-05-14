# ITL Attestation SDK — Package Publishing Guide

## Package Structure

```
src/sdk/
├── pyproject.toml         # Package metadata, dependencies, build config
├── README.md              # Documentation (shown on PyPI)
├── CHANGELOG.md           # Version history
├── LICENSE                # MIT License
├── .gitignore             # Git ignore rules
├── __init__.py            # Package root with version and exports
├── core/                  # Core infrastructure
├── models/                # ORM models
└── repositories/          # Data access layer
```

## Local Development

### Install in editable mode

```bash
cd d:\repos\ITL.ControlPlane.Attestation\src\sdk
pip install -e ".[dev]"
```

This installs the package in editable mode so changes are immediately available.

### Run tests

```bash
pytest
pytest --cov=. --cov-report=html
mypy .
ruff check .
```

## Building the Package

### Prerequisites

```bash
pip install build twine
```

### Build wheel and sdist

```bash
cd d:\repos\ITL.ControlPlane.Attestation\src\sdk
python -m build
```

This creates:
- `dist/itl_attestation_sdk-0.1.0-py3-none-any.whl` (wheel)
- `dist/itl_attestation_sdk-0.1.0.tar.gz` (source distribution)

### Verify the build

```bash
twine check dist/*
```

## Publishing to PyPI

### Test PyPI (recommended first)

```bash
# Upload to test.pypi.org
python -m twine upload --repository testpypi dist/*

# Install from test PyPI to verify
pip install --index-url https://test.pypi.org/simple/ itl-attestation-sdk
```

### Production PyPI

```bash
# Upload to pypi.org (requires PyPI account and token)
python -m twine upload dist/*

# Install from PyPI
pip install itl-attestation-sdk
```

### Using PyPI API Token

Create a `.pypirc` file in your home directory:

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-...

[testpypi]
username = __token__
password = pypi-...
```

## Versioning Workflow

### 1. Update version

Edit `src/sdk/__init__.py`:
```python
__version__ = "0.2.0"  # Bump version
```

### 2. Update CHANGELOG.md

Add new version section:
```markdown
## [0.2.0] - 2026-05-XX

### Added
- New feature X
- New feature Y

### Changed
- Updated dependency Z

### Fixed
- Bug fix A
```

### 3. Commit and tag

```bash
git add src/sdk/__init__.py src/sdk/CHANGELOG.md
git commit -m "chore: bump version to 0.2.0"
git tag v0.2.0
git push origin main --tags
```

### 4. Build and publish

```bash
cd src/sdk
rm -rf dist/  # Clean old builds
python -m build
twine check dist/*
python -m twine upload dist/*
```

## Consuming the SDK

### In another project

```toml
[project]
dependencies = [
    "itl-attestation-sdk>=0.1.0",
]
```

Or:

```bash
pip install itl-attestation-sdk
```

### Usage

```python
from sdk import MachineRow, SqlMachineRepository, config
from sqlmodel import Session, create_engine

engine = create_engine(config.db_url)
session = Session(engine)
repo = SqlMachineRepository(session)
machines = repo.list_all()
```

## CI/CD Integration

### GitHub Actions example

```yaml
name: Publish SDK

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install build twine
      - name: Build package
        run: |
          cd src/sdk
          python -m build
      - name: Publish to PyPI
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
        run: |
          cd src/sdk
          python -m twine upload dist/*
```

## Package Metadata

- **Name**: `itl-attestation-sdk`
- **Version**: `0.1.0`
- **License**: MIT
- **Python**: `>=3.10`
- **Homepage**: https://github.com/ITLusions/ITL.ControlPlane.Attestation
- **Author**: ITLusions <info@itlusions.com>

## Dependencies

**Required**:
- sqlmodel>=0.0.16
- sqlalchemy[asyncio]>=2.0.0
- aiosqlite>=0.19.0
- pydantic>=2.0.0
- pydantic-settings>=2.0.0

**Optional (dev)**:
- pytest>=8.0.0
- pytest-asyncio>=0.23.0
- pytest-cov>=4.1.0
- mypy>=1.8.0
- ruff>=0.2.0
- types-sqlalchemy
