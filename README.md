# CGMES MJAP Interface

A Windows desktop front end for CGMES / CIMLA processing and Excel export.

> **Current phase: interface only.**
> The conversion backend is not implemented. Pressing **Start Conversion** runs
> the real worker thread and the real state machine, then fails with
> `CGMES/CIMLA backend integration has not been implemented yet.` That is
> deliberate: the application never suggests a conversion happened when none did.

## Running

```bash
uv sync --extra gui
uv run cgmes-parser            # or: uv run python -m cgmesparser
uv run cgmes-parser --demo     # walk the stages with a backend that does nothing
```

`--demo` exists to exercise the interface. It writes no files, reports zero for
every count, and prefixes every line it logs with `[DEMO]`.

## Architecture

```
        PySide6 widgets            presentation only, no decisions
                |
        ConversionController       state machine, thread lifecycle
                |
        ConversionService          Protocol - the backend seam
                |
        (later: your converter, behind one adapter)
```

Two rules keep the layers apart:

1. **`core/` imports no Qt.** Validation, the state machine and the button
   matrix are plain Python, tested without a `QApplication`.
2. **Widgets make no decisions.** They emit what the user did and render what
   they are handed. No widget judges a path or enables itself.

```
src/cgmesparser/
├── app.py                 composition root - chooses the service
├── mainWindow.py          assembly and signal wiring, no rules
├── core/                  Qt-free: states, request, validation, transitions
├── services/              the ConversionService Protocol and its stand-ins
├── controller/            controller + QThread worker
├── widgets/               one module per card
├── dialogs/               preferences
└── resources/             tokens, stylesheet, SVG icons (all Python, no data files)
```

### Adding the conversion backend

Write one adapter implementing the Protocol in `services/protocol.py`:

```python
class CimlaConversionService:
    def convert(self, request, sink, token) -> ConversionOutcome:
        sink.stage(ProcessingStage.LOAD_MODELS, StageState.ACTIVE)
        token.raiseIfCancelled()
        ...
        return ConversionOutcome(...)
```

Then return it from `buildService` in `app.py`. That adapter is the only file
that imports both the interface and the converter; no widget, controller or core
module changes. Cancellation is cooperative - poll `token` between units of work
and raise `ConversionCancelled`; nothing is ever forcibly terminated.

Domain-specific input validation slots into `validateRequest(request,
extraCheckers=...)` without touching the interface.

## Application states

```
IDLE ──validate──▶ VALIDATING ──valid──▶ READY ──start──▶ RUNNING ──▶ SUCCEEDED | FAILED
                          └──invalid───▶ IDLE                └──stop──▶ STOPPING ──▶ IDLE
any path changed ──▶ IDLE        (a previous validation no longer applies)
```

Every button's enabled state comes from one function,
`core.transitions.buttonStatesFor`. `ActionBar.applyButtonStates` is the only
place `setEnabled` is called on an action button.

## Validation

Filesystem-level only in this phase: existence, file-versus-directory, `.zip`
suffix, readability, and output-directory writability. An output directory that
already exists is a **warning**, not an error - it is usable, but previous output
in it may be overwritten.

Warnings never block a conversion. Only errors do.

## Development

```bash
uv sync --extra gui
uv run ruff check .
uv run pytest                  # headless; Qt runs offscreen
```

Identifiers are camelCase throughout. Ruff's `N` (pep8-naming) rules are
deliberately not enabled - see the comment in `pyproject.toml`.

## Building the Windows executable

```powershell
.\scripts\build.ps1            # Windows
```

```bash
./scripts/build.sh             # Linux / macOS, native binary
```

Both run the same sequence: sync, `ruff check`, `pytest`, PyInstaller, SHA256.
A local build and a pipeline build are therefore the same build.

`build.sh` produces a native binary for the host it runs on. A Windows `.exe`
requires a Windows host - PyInstaller does not cross-compile.

## Releasing

```powershell
.\scripts\release.ps1 -Version 1.2.0
```

```bash
./scripts/release.sh 1.2.0
```

The script updates `version.py` and `pyproject.toml` together, commits, tags
`v1.2.0` and pushes. Pushing the tag is what starts a release build.

`azure-pipelines.yml` then:

1. **Verify** on `ubuntu-latest` - ruff and pytest, on every push, PR and tag.
2. **Package** on `windows-latest`, only for `v*` tags - checks the tag matches
   `version.py`, builds the exe, publishes it as a pipeline artifact, then
   commits it into `releases/` on `main`.

### One-time Azure DevOps setup

The pipeline pushes the built exe back to the repository, so the build identity
needs permission to do that:

> Project Settings → Repositories → *your repo* → Security →
> **&lt;Project&gt; Build Service** → set **Contribute** to **Allow**.

Without this the Package stage fails with a 403 on the final push.

The release commit ends with `[skip ci]`, and the CI trigger excludes
`releases/**`, so the pipeline cannot retrigger itself.

### A note on repository size

Built executables are committed to `releases/` with versioned filenames. The
one-file build measures **~36 MB** (the PyInstaller spec excludes the Qt modules
this application does not use, roughly halving it). Git keeps every past blob
forever, so the repository grows by about that much per release and never
shrinks - around 360 MB after ten releases.

If that becomes a problem, move `releases/*.exe` to Git LFS; Azure Repos
supports it natively. History already written stays written, so the decision is
cheaper to make early than late.
