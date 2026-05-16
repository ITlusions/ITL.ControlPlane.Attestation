---
layout: default
title: Extension Development
category: Advanced
description: Step-by-step guide to building AttestationExtensions and CLI plugins
---

# Extension Development Guide

The attestation platform has two independent extension points:

| Extension type | Extends | Base class | Entry point group |
|---|---|---|---|
| `AttestationExtension` | FastAPI service (routes, DB models, lifecycle) | `itl-attestation-sdk` | `attestation_extensions` |
| `CliPlugin` | Click CLI (command groups) | `itl-attestation-sdk[cli]` | `attestation_cli_plugins` |

Both are discovered automatically at startup via Python entry points — no code changes to the core are required. A single pip package can ship both an `AttestationExtension` and a `CliPlugin` at the same time.

---

## Part 1 — AttestationExtension

### What it can contribute

| Method | Called when | Purpose |
|---|---|---|
| `get_models()` | Before `create_all()` | Register SQLModel ORM classes so tables are created |
| `on_startup()` | After `create_all()` | Initialisation (seed data, background tasks, etc.) |
| `get_router()` | During app setup | Mount FastAPI routes onto the service |
| `on_shutdown()` | Service shutdown | Cleanup (close connections, flush buffers) |

Only `name`, `version`, `description`, and `get_router()` are required. All lifecycle methods have a default no-op implementation.

---

### Step 1 — Install the SDK

```bash
pip install itl-attestation-sdk
```

---

### Step 2 — Implement the extension

```python
# mypackage/extension.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import SQLModel, Field, Session, select
from sdk import AttestationExtension


# ── Database model ─────────────────────────────────────────────────────────────
# Table names must be prefixed with "extension_" to avoid collisions.

class TagRow(SQLModel, table=True):
    __tablename__ = "extension_myext_tags"

    tag_id: Optional[int] = Field(default=None, primary_key=True)
    machine_id: str = Field(index=True)
    label: str
    created_by: str


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class TagCreate(SQLModel):
    label: str

class TagRead(SQLModel):
    tag_id: int
    machine_id: str
    label: str
    created_by: str


# ── Extension class ────────────────────────────────────────────────────────────

class MyExtension(AttestationExtension):
    """Tag machines with arbitrary labels."""

    @property
    def name(self) -> str:
        return "my_ext"          # snake_case, used as registry key and table prefix

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Attach custom labels to registered machines"

    # ── Models ─────────────────────────────────────────────────────────────────

    def get_models(self) -> list[type]:
        # Return all SQLModel table classes so they are registered
        # in SQLModel.metadata before create_all() runs.
        return [TagRow]

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def on_startup(self) -> None:
        # Optional: run once after tables are created.
        pass

    async def on_shutdown(self) -> None:
        # Optional: run once on service shutdown.
        pass

    # ── Routes ─────────────────────────────────────────────────────────────────

    def get_router(self) -> APIRouter:
        router = APIRouter(
            prefix="/api/v1/myext",
            tags=["my-extension"],
        )

        @router.post("/machines/{machine_id}/tags", response_model=TagRead)
        async def create_tag(
            machine_id: str,
            body: TagCreate,
            session: Session = Depends(get_session),
        ) -> TagRow:
            tag = TagRow(
                machine_id=machine_id,
                label=body.label,
                created_by="operator",   # replace with real auth principal
            )
            session.add(tag)
            session.commit()
            session.refresh(tag)
            return tag

        @router.get("/machines/{machine_id}/tags", response_model=list[TagRead])
        async def list_tags(
            machine_id: str,
            session: Session = Depends(get_session),
        ) -> list[TagRow]:
            return session.exec(
                select(TagRow).where(TagRow.machine_id == machine_id)
            ).all()

        @router.delete("/machines/{machine_id}/tags/{tag_id}", status_code=204)
        async def delete_tag(
            machine_id: str,
            tag_id: int,
            session: Session = Depends(get_session),
        ) -> None:
            tag = session.get(TagRow, tag_id)
            if not tag or tag.machine_id != machine_id:
                raise HTTPException(status_code=404, detail="Tag not found")
            session.delete(tag)
            session.commit()

        return router


# ── Helper (replace with the shared get_session from the service) ──────────────

def get_session():
    # In practice, import this from attestation.core.database.
    # Shown here as a placeholder so the example is self-contained.
    raise NotImplementedError("wire up the real session factory")
```

---

### Step 3 — Declare the entry point

```toml
# mypackage/pyproject.toml
[project.entry-points."attestation_extensions"]
my-ext = "mypackage.extension:MyExtension"
```

---

### Step 4 — Install and verify

```bash
pip install -e .
# Restart the service — look for this in the logs:
# [Extension] Loaded external: my_ext v1.0.0
```

Confirm the route is live:

```bash
curl http://localhost:9000/api/v1/myext/machines/<uuid>/tags
```

And that the extension appears in the registry:

```bash
curl http://localhost:9000/api/v1/extensions
# {"my_ext": {"version": "1.0.0", "description": "Attach custom labels..."}}
```

---

### Checklist

- [ ] `name` is snake\_case and unique across installed extensions
- [ ] All table names are prefixed with `extension_<name>_`
- [ ] `get_models()` returns every SQLModel table class
- [ ] `get_router()` uses a unique URL prefix (`/api/v1/<name>/...`)
- [ ] Extension is stateless — all state lives in the database or a managed external system
- [ ] `on_startup` / `on_shutdown` are idempotent (safe to call multiple times)

---

## Part 2 — CLI Plugin

### What it can contribute

A `CliPlugin` attaches one or more Click command groups to the root `attestation` CLI. Commands registered via a plugin appear in `attestation --help` and are invoked exactly like built-in commands.

---

### Step 1 — Install the SDK (CLI extra)

```bash
pip install "itl-attestation-sdk[cli]"
```

`click` is not a hard dependency of the core SDK. The `[cli]` extra pulls it in.

---

### Step 2 — Implement the plugin

```python
# mypackage/cli_plugin.py
from __future__ import annotations

import click
from sdk.extensions import CliPlugin


class MyCliPlugin(CliPlugin):
    """CLI commands for the my-ext extension."""

    name = "my-extension"
    version = "1.0.0"
    description = "Tag machines with custom labels"

    def register(self, cli: click.Group) -> None:
        """Called once at CLI startup. Attach all command groups here."""

        @cli.group("tag")
        def tag_group() -> None:
            """Manage machine tags."""

        @tag_group.command("list")
        @click.argument("machine_id")
        @click.option("--url", envvar="ATTESTATION_API_URL", default="http://localhost:9000")
        @click.option("--token", envvar="ATTESTATION_TOKEN", default=None)
        def tag_list(machine_id: str, url: str, token: str | None) -> None:
            """List tags for MACHINE_ID."""
            from cli.api_client import AttestationClient

            client = AttestationClient(base_url=url, token=token)
            result = client.get(f"/api/v1/myext/machines/{machine_id}/tags")
            if not result:
                click.echo("No tags found.")
                return
            for tag in result:
                click.echo(f"  [{tag['tag_id']}] {tag['label']}")

        @tag_group.command("add")
        @click.argument("machine_id")
        @click.argument("label")
        @click.option("--url", envvar="ATTESTATION_API_URL", default="http://localhost:9000")
        @click.option("--token", envvar="ATTESTATION_TOKEN", default=None)
        def tag_add(machine_id: str, label: str, url: str, token: str | None) -> None:
            """Add LABEL to MACHINE_ID."""
            from cli.api_client import AttestationClient

            client = AttestationClient(base_url=url, token=token)
            result = client.post(
                f"/api/v1/myext/machines/{machine_id}/tags",
                json={"label": label},
            )
            click.echo(f"Created tag {result['tag_id']}: {result['label']}")

        @tag_group.command("remove")
        @click.argument("machine_id")
        @click.argument("tag_id", type=int)
        @click.option("--url", envvar="ATTESTATION_API_URL", default="http://localhost:9000")
        @click.option("--token", envvar="ATTESTATION_TOKEN", default=None)
        def tag_remove(machine_id: str, tag_id: int, url: str, token: str | None) -> None:
            """Remove TAG_ID from MACHINE_ID."""
            from cli.api_client import AttestationClient

            client = AttestationClient(base_url=url, token=token)
            client.delete(f"/api/v1/myext/machines/{machine_id}/tags/{tag_id}")
            click.echo(f"Deleted tag {tag_id}.")
```

---

### Step 3 — Using `get_token()` for authenticated commands

If the command needs to authenticate against Keycloak (not just pass a raw token), import `get_token` from the CLI package:

```python
from cli.auth import get_token

def register(self, cli: click.Group) -> None:

    @cli.group("tag")
    def tag_group() -> None:
        """Manage machine tags."""

    @tag_group.command("list")
    @click.argument("machine_id")
    @click.option("--url", envvar="ATTESTATION_API_URL", default="http://localhost:9000")
    def tag_list(machine_id: str, url: str) -> None:
        token = get_token()  # reads from token cache, exits with message if not logged in
        from cli.api_client import AttestationClient
        client = AttestationClient(base_url=url, token=token)
        ...
```

`get_token()` reads the token cache written by `attestation auth login`. If no valid token exists it prints a message and calls `sys.exit(1)` — no need to handle it manually.

---

### Step 4 — Declare the entry point

```toml
# mypackage/pyproject.toml
[project.entry-points."attestation_cli_plugins"]
my-ext = "mypackage.cli_plugin:MyCliPlugin"
```

---

### Step 5 — Install and verify

```bash
pip install -e .
attestation --help
# Usage: attestation [OPTIONS] COMMAND [ARGS]...
# ...
#   tag   Manage machine tags.        ← appears automatically
```

Test a command:

```bash
attestation tag list <machine-uuid>
attestation tag add  <machine-uuid> production
attestation tag remove <machine-uuid> 3
```

---

### Checklist

- [ ] `name` matches the entry point key (kebab-case by convention)
- [ ] `register(cli)` only attaches commands — no I/O at import time
- [ ] Lazy-import `AttestationClient` inside the command function (not at module level) — avoids import errors when only the service wheel is installed without the CLI
- [ ] All commands accept `--url` (with `ATTESTATION_API_URL` envvar) and `--token`
- [ ] Failed discovery never crashes the CLI — the plugin loader already catches exceptions per plugin

---

## Part 3 — Shipping both in one package

A single package that ships a service extension **and** a CLI plugin:

```
mypackage/
├── pyproject.toml
├── src/
│   └── mypackage/
│       ├── __init__.py
│       ├── extension.py     # AttestationExtension subclass
│       └── cli_plugin.py    # CliPlugin subclass
```

```toml
# pyproject.toml
[project]
name = "itl-attestation-my-ext"
version = "1.0.0"
requires-python = ">=3.10"
dependencies = [
    "itl-attestation-sdk>=0.1.0",
]

[project.optional-dependencies]
cli = ["itl-attestation-sdk[cli]>=0.1.0"]

[project.entry-points."attestation_extensions"]
my-ext = "mypackage.extension:MyExtension"

[project.entry-points."attestation_cli_plugins"]
my-ext = "mypackage.cli_plugin:MyCliPlugin"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Install scenarios:

```bash
# Service only (no click dependency)
pip install itl-attestation-my-ext

# Service + CLI
pip install "itl-attestation-my-ext[cli]"
```

Both entry points are always registered by pip regardless of extras. The `[cli]` extra only controls whether `click` is installed. The `CliPlugin` import is guarded in the SDK (`try: from .cli import CliPlugin`) so importing the SDK without click does not fail.

---

## Part 4 — Testing

### Unit-testing an AttestationExtension

```python
# tests/test_extension.py
import pytest
from sqlmodel import SQLModel, create_engine, Session
from mypackage.extension import MyExtension, TagRow


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_get_models_registers_table():
    ext = MyExtension()
    assert TagRow in ext.get_models()


def test_router_has_expected_routes():
    ext = MyExtension()
    router = ext.get_router()
    paths = {r.path for r in router.routes}
    assert "/api/v1/myext/machines/{machine_id}/tags" in paths
```

### Unit-testing a CliPlugin

```python
# tests/test_cli_plugin.py
import click
from click.testing import CliRunner
from mypackage.cli_plugin import MyCliPlugin


def _build_cli() -> click.Group:
    @click.group()
    def cli():
        pass
    MyCliPlugin().register(cli)
    return cli


def test_tag_group_registered():
    cli = _build_cli()
    assert "tag" in [c.name for c in cli.commands.values()]


def test_tag_list_help():
    runner = CliRunner()
    result = runner.invoke(_build_cli(), ["tag", "list", "--help"])
    assert result.exit_code == 0
    assert "MACHINE_ID" in result.output
```

---

## Part 5 — Installing a custom extension

Extensions are installed into the Python environment where the service and/or CLI run. The service and CLI are typically in different environments (separate containers or venvs), so each must have the package installed.

### Install sources

**From PyPI (published package)**

```bash
pip install itl-attestation-my-ext
# With CLI support:
pip install "itl-attestation-my-ext[cli]"
```

**From a local directory (development)**

```bash
# Editable install — changes to source are reflected immediately (no reinstall needed).
pip install -e /path/to/mypackage
pip install -e "/path/to/mypackage[cli]"
```

**From a wheel file**

```bash
pip install itl_attestation_my_ext-1.0.0-py3-none-any.whl
```

**From a Git repository**

```bash
# Latest commit on main branch
pip install "git+https://github.com/example/itl-attestation-my-ext.git"

# Specific tag or branch
pip install "git+https://github.com/example/itl-attestation-my-ext.git@v1.2.0"
pip install "git+https://github.com/example/itl-attestation-my-ext.git@feature/my-branch"

# With CLI extra
pip install "itl-attestation-my-ext[cli] @ git+https://github.com/example/itl-attestation-my-ext.git@v1.2.0"
```

---

### Installing into the service (Docker)

The service runs in a container. The extension must be installed inside that container's environment.

**Option A — Add to the Dockerfile**

```dockerfile
# In the attestation service Dockerfile, after the base install:
RUN pip install itl-attestation-my-ext==1.0.0
```

Rebuild and redeploy the image.

**Option B — Mount a requirements file (Docker Compose)**

```yaml
# docker-compose.yml
services:
  attestation:
    image: itl-controlplane-attestation:latest
    volumes:
      - ./extensions-requirements.txt:/extensions-requirements.txt
    command: >
      sh -c "pip install -r /extensions-requirements.txt &&
             uvicorn attestation.core.app:app --host 0.0.0.0 --port 9000"
```

```
# extensions-requirements.txt
itl-attestation-my-ext==1.0.0
itl-attestation-another-ext>=2.0.0
```

**Option C — Editable mount (development only)**

```yaml
services:
  attestation:
    image: itl-controlplane-attestation:latest
    volumes:
      - /path/to/mypackage:/opt/mypackage
    command: >
      sh -c "pip install -e /opt/mypackage &&
             uvicorn attestation.core.app:app --host 0.0.0.0 --port 9000"
```

---

### Installing on a workstation (CLI only)

If your workstation only has `itl-attestation-cli` installed — no service, no Docker — only the `[cli]` extra is needed. The `AttestationExtension` part of the package is ignored; only the `CliPlugin` entry point is used.

**Step 1 — Find where the CLI is installed**

```powershell
# Windows
where.exe attestation
# e.g. C:\Users\you\AppData\Local\Programs\Python\Python312\Scripts\attestation.exe

# macOS / Linux
which attestation
# e.g. /home/you/.venv/bin/attestation
```

**Step 2 — Install the plugin into that same environment**

```bash
# If attestation is on the active PATH / venv:
pip install "itl-attestation-my-ext[cli]"

# If you need to be explicit about which pip:
C:\Users\you\AppData\Local\Programs\Python\Python312\Scripts\pip install "itl-attestation-my-ext[cli]"
```

**From a local folder (development):**

```bash
pip install -e "C:\path\to\mypackage[cli]"
```

**From a Git repository:**

```bash
pip install "itl-attestation-my-ext[cli] @ git+https://github.com/example/itl-attestation-my-ext.git@v1.0.0"
```

**Step 3 — Verify**

```bash
attestation --help
# The plugin's command group must appear in the list.

attestation tag --help
# Shows the plugin's subcommands.
```

**Step 4 — Point the CLI at the remote service**

The plugin commands call the attestation REST API. On a workstation the URL is not `localhost` — set it once via environment variable so you don't have to pass `--url` on every command:

```powershell
# Windows (current session)
$env:ATTESTATION_API_URL = "https://attestation.itl.local:9000"
$env:ATTESTATION_TOKEN   = "eyJ..."    # or use: attestation auth login

# Windows (persistent, user scope)
[System.Environment]::SetEnvironmentVariable("ATTESTATION_API_URL", "https://attestation.itl.local:9000", "User")
```

```bash
# macOS / Linux
export ATTESTATION_API_URL="https://attestation.itl.local:9000"
```

Or add it to a `.env` file and load it with your shell profile.

**Uninstalling:**

```bash
pip uninstall itl-attestation-my-ext
# Takes effect on the next attestation invocation — no restart needed.
```

---

### Verifying registration

**Service side** — check the logs at startup:

```
[Extension] Loaded external: my_ext v1.0.0
```

Or query the extensions registry endpoint:

```bash
curl http://localhost:9000/api/v1/extensions | python -m json.tool
```

Expected output:

```json
{
  "my_ext": {
    "version": "1.0.0",
    "description": "Attach custom labels to registered machines"
  }
}
```

**CLI side** — check the help output:

```bash
attestation --help
# ...
#   tag   Manage machine tags.     ← plugin command group appears here
```

Or list loaded plugins explicitly (if the `debug` command group is enabled):

```bash
pip show itl-attestation-my-ext
# Check that the package is installed and shows the right version.

python -c "
from importlib.metadata import entry_points
eps = entry_points(group='attestation_cli_plugins')
for ep in eps:
    print(ep.name, '->', ep.value)
"
# my-ext -> mypackage.cli_plugin:MyCliPlugin
```

---

### Uninstalling an extension

```bash
pip uninstall itl-attestation-my-ext
```

**Service**: restart the service after uninstalling. The extension will no longer appear in the logs or the `/api/v1/extensions` response.

**CLI**: takes effect on the next invocation. The command group disappears from `attestation --help` immediately.

> **Database tables are not dropped on uninstall.** If the extension created database tables (via `get_models()`), those tables remain in the database. Run a migration or manual `DROP TABLE` if the data is no longer needed.

---

### Pinning and dependency management

It is strongly recommended to pin extension versions in production to avoid unexpected behaviour from upstream updates.

```
# requirements-extensions.txt
itl-attestation-my-ext==1.2.3
itl-attestation-another-ext==0.9.1
```

Combine with the core service requirements:

```bash
pip install \
  itl-controlplane-attestation==1.0.0 \
  -r requirements-extensions.txt
```

---

## Reference

### `AttestationExtension` — full interface

```python
class AttestationExtension(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...         # snake_case, unique

    @property
    @abstractmethod
    def version(self) -> str: ...      # semver

    @property
    @abstractmethod
    def description(self) -> str: ...  # one line

    @abstractmethod
    def get_router(self) -> Optional[APIRouter]: ...

    @abstractmethod
    def get_models(self) -> list[type]: ...

    async def on_startup(self) -> None: ...   # optional
    async def on_shutdown(self) -> None: ...  # optional
```

### `CliPlugin` — full interface

```python
class CliPlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...         # kebab-case, matches entry point key

    @property
    @abstractmethod
    def version(self) -> str: ...      # semver

    @property
    def description(self) -> str:      # optional, shown in plugin list
        return ""

    @abstractmethod
    def register(self, cli: click.Group) -> None: ...
```

### Entry point groups

| Group | Consumed by |
|---|---|
| `attestation_extensions` | Service lifespan — `discover_extensions()` in `app.py` |
| `attestation_cli_plugins` | CLI startup — `discover_and_register_plugins()` in `__main__.py` |

### Context passed to CLI commands

Every Click command registered via a plugin has access to `ctx.obj` (if `pass_context` is used), which contains the same context dict that built-in commands receive. Currently this dict is empty — use environment variables (`ATTESTATION_API_URL`, `ATTESTATION_TOKEN`) as the primary configuration mechanism.
