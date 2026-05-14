# Publishing Guide — ITL Attestation CLI

Guide for building and publishing the ITL Attestation CLI package to PyPI.

## Prerequisites

```bash
pip install build twine
```

## Versioning Workflow

The CLI follows [Semantic Versioning 2.0.0](https://semver.org/):

- **MAJOR** (`1.0.0`) — Incompatible API changes
- **MINOR** (`0.1.0`) — Backwards-compatible functionality additions
- **PATCH** (`0.1.1`) — Backwards-compatible bug fixes

### Release Types

| Version format | Purpose | Publish to |
|---|---|---|
| `0.1.0` | Stable release | PyPI |
| `0.1.1-rc.1` | Release candidate | TestPyPI |
| `0.2.0-dev.123` | Development build | TestPyPI |

## Build Process

### 1. Update version

Edit `__init__.py`:
```python
__version__ = "0.1.0"
```

Edit `pyproject.toml`:
```toml
[project]
version = "0.1.0"
```

### 2. Update CHANGELOG

Edit `CHANGELOG.md` and document changes under new version heading.

### 3. Clean previous builds

```bash
rm -rf dist/ build/ *.egg-info
```

### 4. Build packages

```bash
python -m build
```

This creates:
- `dist/itl_attestation_cli-0.1.0-py3-none-any.whl` — Wheel package
- `dist/itl_attestation_cli-0.1.0.tar.gz` — Source distribution

### 5. Validate packages

```bash
twine check dist/*
```

Expected output:
```
Checking dist/itl_attestation_cli-0.1.0-py3-none-any.whl: PASSED
Checking dist/itl_attestation_cli-0.1.0.tar.gz: PASSED
```

## Publishing

### TestPyPI (pre-release testing)

```bash
twine upload --repository testpypi dist/*
```

Test installation:
```bash
pip install --index-url https://test.pypi.org/simple/ itl-attestation-cli
```

### PyPI (production release)

```bash
twine upload dist/*
```

Production installation:
```bash
pip install itl-attestation-cli
```

## Authentication

### Option 1: PyPI API Token (recommended)

Create a token at https://pypi.org/manage/account/token/

Store in `~/.pypirc`:
```ini
[pypi]
username = __token__
password = pypi-...your-token...

[testpypi]
username = __token__
password = pypi-...your-token...
```

### Option 2: Environment variables

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-...your-token...
twine upload dist/*
```

### Option 3: OIDC Trusted Publisher (GitHub Actions)

No tokens needed — configure Trusted Publisher on PyPI:
1. Go to https://pypi.org/manage/project/itl-attestation-cli/settings/publishing/
2. Add GitHub repository: `ITLusions/ITL.ControlPlane.Attestation`
3. Set workflow name: `publish.yml`
4. Set environment name: `pypi`

GitHub Actions workflow handles publishing automatically.

## CI/CD Pipeline

### Two-stage workflow

**Stage 1: `ci.yml`** (on push, PR, manual dispatch)
- Detect version from `__init__.py`
- Lint with ruff and mypy
- Run tests with pytest
- Build wheel and sdist
- Store artifacts
- Auto-tag release branches and main
- Create GitHub Release

**Stage 2: `publish.yml`** (on release published)
- Download artifacts from CI
- Publish to PyPI (stable) or TestPyPI (pre-release)
- No secrets required (OIDC Trusted Publisher)

### Branch strategy

| Branch | CI behavior | Auto-tag | Publish |
|---|---|---|---|
| `feature/**`, `hotfix/**`, `develop` | Lint + test + build | — | — |
| `release/**` | Lint + test + build | `cli-v0.1.0-rc.N` | TestPyPI |
| `main` | Lint + test + build | `cli-v0.1.0` | PyPI |

### Workflow example

```yaml
name: Publish CLI

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      id-token: write  # OIDC token for PyPI
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: cli-wheel
          path: dist/

      - name: Publish to PyPI
        if: ${{ !github.event.release.prerelease }}
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          packages-dir: dist/

      - name: Publish to TestPyPI
        if: ${{ github.event.release.prerelease }}
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          repository-url: https://test.pypi.org/legacy/
          packages-dir: dist/
```

## Manual Publishing Steps

1. Checkout main/release branch
2. Update version in `__init__.py` and `pyproject.toml`
3. Update `CHANGELOG.md`
4. Commit: `git commit -am "Release CLI v0.1.0"`
5. Tag: `git tag cli-v0.1.0`
6. Push: `git push && git push --tags`
7. Build: `python -m build`
8. Validate: `twine check dist/*`
9. Publish: `twine upload dist/*`

## Post-Release

1. Verify installation: `pip install itl-attestation-cli`
2. Test CLI: `attestation --version`
3. Update documentation links if needed
4. Announce release on communication channels

## Troubleshooting

### "File already exists" error

PyPI does not allow re-uploading the same version. Increment version and rebuild.

### "Invalid distribution" error

Run `twine check dist/*` to identify issues. Common problems:
- Missing required metadata in `pyproject.toml`
- Invalid README format
- Missing LICENSE file

### Authentication failed

Check token permissions and expiry. Recreate token at https://pypi.org/manage/account/token/

---

**Last updated**: 12 May 2026
