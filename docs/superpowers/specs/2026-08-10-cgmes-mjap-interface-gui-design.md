# CGMES MJAP Interface — Desktop GUI Shell

**Date:** 2026-08-10
**Status:** Approved for planning
**Scope:** Phase 1 — GUI shell, architecture and packaging. No CGMES/CIMLA business logic.

---

## 1. Purpose

Build a production-quality PySide6 desktop application for Windows that presents the
CGMES MJAP conversion workflow: four input selections, filesystem validation, a six-stage
processing view, message log, output summary and session information.

This phase delivers **the application shell and its integration seams**. The conversion
backend is deliberately absent. When it arrives it must connect through a single, already
defined interface without the GUI being redesigned.

### 1.1 Explicit non-goals

The following are **out of scope** and must not be invented, approximated or simulated in
production code paths:

- Loading, parsing or merging CGMES models
- Any CIMLA invocation
- Any mapping of the six UI stages onto real conversion operations
- Real progress percentages
- Domain-specific (semantic) input validation
- Writing Excel files
- Fabricated log lines that imply processing occurred

Where behaviour is unavailable, the code raises `NotImplementedError`, performs an explicit
no-op, or logs a clearly marked message. It never pretends a conversion succeeded.

---

## 2. Settled decisions

| Question | Decision |
| --- | --- |
| Code location | New sibling package `src/cgmesmjap/` in this repository |
| Naming convention | camelCase for identifiers, matching `cgmes2excel` |
| Python | `requires-python = ">=3.12"` (unchanged) |
| GUI dependency | PySide6 in an optional `gui` extra, so the CLI stays lightweight |
| Backend seam | `ConversionService` Protocol; default is `UnimplementedConversionService` |
| Demo mode | `DemoConversionService`, reachable only via `--demo` |
| Message signals | One `messageLogged(LogRecord)` carrying a level, not three parallel signals |
| CI/CD | Azure DevOps multi-stage `azure-pipelines.yml` |
| Release trigger | Git tag `v*` |
| Exe storage | Committed to `releases/` with versioned filenames, plain git (no LFS) |
| Exe delivery | Pipeline commits the exe back to `main` automatically |
| Build agent | Microsoft-hosted: `ubuntu-latest` to verify, `windows-latest` to package |

### 2.1 Accepted risk

The exe is committed to git with versioned filenames and no LFS. A PySide6 one-file
PyInstaller build is roughly 60–120 MB, and git retains every past blob permanently. The
repository will grow by approximately one exe per release and will not shrink. This was
raised and accepted. Mitigation available later without redesign: move `releases/*.exe`
to Git LFS via `.gitattributes`, which Azure Repos supports natively.

---

## 3. Architecture

```
        PySide6 widgets            presentation only, no decisions
                |
        ConversionController       state machine, thread lifecycle
                |
        ConversionService          Protocol — the backend seam
                |
        (phase 2: CimlaConversionService -> cgmes2excel)
```

Two rules hold the layering in place:

1. **`core/` imports no Qt.** Validation, the state machine, the button matrix and the
   session snapshot are pure Python and are tested without a `QApplication`.
2. **Widgets make no decisions.** They emit intent and render what they are given. No
   widget constructs a `ConversionRequest`, judges a path, or calls `setEnabled` on itself
   based on application state.

Everything in `core/` and `services/protocol.py` is designed to survive phase 2 untouched.

### 3.1 Package layout

```
src/cgmesmjap/
├── __init__.py
├── __main__.py                 python -m cgmesmjap
├── app.py                      createApplication(), main(argv) -> int
├── version.py                  __version__ — single source of truth
├── mainWindow.py               assembles widgets, wires signals, closeEvent
├── core/
│   ├── states.py               ApplicationState, ProcessingStage, StageState, MessageLevel, InputRole, CheckStatus
│   ├── request.py              ConversionRequest
│   ├── validation.py           InputCheck, ValidationReport, validateRequest()
│   ├── result.py               ConversionOutcome, StageUpdate, LogRecord
│   ├── session.py              SessionInfo
│   ├── transitions.py          nextState(), ButtonStates, buttonStatesFor()
│   └── settings.py             SettingsStore, Preferences
├── services/
│   ├── protocol.py             ConversionService, ProgressSink, CancellationToken
│   ├── unimplemented.py        UnimplementedConversionService
│   └── demo.py                 DemoConversionService  (opt-in only)
├── controller/
│   ├── conversion.py           ConversionController(QObject)
│   └── worker.py               ConversionWorker(QObject)
├── widgets/
│   ├── common.py               Card, SectionBadge, KeyValueRow, IconLabel
│   ├── header.py               HeaderBanner
│   ├── inputSources.py         InputSourcesCard, PathSelectorRow, ValidationStrip
│   ├── processing.py           ProcessingCard, StageStepper
│   ├── messages.py             MessagesCard, MessageLogModel
│   ├── output.py               OutputCard
│   ├── session.py              SessionInfoCard
│   └── actionBar.py            ActionBar
├── dialogs/
│   └── preferences.py          PreferencesDialog
└── resources/
    ├── __init__.py             loadStylesheet(), icon(name)
    ├── tokens.py               colour / spacing / typography constants
    ├── theme.qss               QSS template, formatted from tokens
    └── icons/*.svg             ~19 hand-authored SVGs, no external assets
```

---

## 4. Core domain

### 4.1 Enumerations (`core/states.py`)

```python
class ApplicationState(Enum):
    IDLE, VALIDATING, READY, RUNNING, STOPPING, SUCCEEDED, FAILED

class ProcessingStage(Enum):
    LOAD_MODELS, VALIDATE_INPUTS, EXTRACT_LINES,
    CLASSIFY_SUBSTATIONS, MERGE_DATA, EXCEL_EXPORT

class StageState(Enum):
    PENDING, ACTIVE, COMPLETED, FAILED

class MessageLevel(Enum):
    INFO, WARNING, ERROR

class InputRole(Enum):
    PROFILE_ZIP, SNAPSHOT_DATASET, CIM_CACHE_DATASET, OUTPUT_DIRECTORY

class CheckStatus(Enum):
    OK, WARNING, ERROR
```

`ProcessingStage` members carry a display label (`"Load Models"`, …) and are ordered.
They are **UI definitions only**; no mapping onto backend operations exists in this phase.

### 4.2 `ConversionRequest` (`core/request.py`)

Frozen dataclass of four optional paths, one per `InputRole`.

```python
@dataclass(frozen=True, slots=True)
class ConversionRequest:
    profileZip: Path | None = None
    snapshotDataset: Path | None = None
    cimCacheDataset: Path | None = None
    outputDirectory: Path | None = None

    def withPath(self, role: InputRole, path: Path | None) -> ConversionRequest: ...
    def pathFor(self, role: InputRole) -> Path | None: ...
    @property
    def isComplete(self) -> bool:   # all four set
```

Immutable, so a state change is always an explicit replacement and never an aliasing bug.

### 4.3 Validation (`core/validation.py`)

Pure function, filesystem-level only, no Qt, no CGMES knowledge.

```python
@dataclass(frozen=True, slots=True)
class InputCheck:
    role: InputRole
    status: CheckStatus
    message: str

@dataclass(frozen=True, slots=True)
class ValidationReport:
    checks: tuple[InputCheck, ...]
    @property
    def isValid(self) -> bool:      # no check has status ERROR
    @property
    def summary(self) -> str:       # "Inputs validated" / "N problem(s) found"

def validateRequest(request: ConversionRequest) -> ValidationReport: ...
```

Rules per role:

| Role | Condition | Status | Message |
| --- | --- | --- | --- |
| Any | not selected | ERROR | `Not selected` |
| Profile ZIP | missing on disk | ERROR | `File does not exist` |
| Profile ZIP | not a file | ERROR | `Not a file` |
| Profile ZIP | suffix is not `.zip` | ERROR | `Not a .zip archive` |
| Profile ZIP | unreadable | ERROR | `File is not readable` |
| Profile ZIP | zero bytes | ERROR | `File is empty` |
| Profile ZIP | otherwise | OK | `OK` |
| Snapshot / CIM cache | missing on disk | ERROR | `Path does not exist` |
| Snapshot / CIM cache | unreadable | ERROR | `Path is not readable` |
| Snapshot / CIM cache | directory, empty | WARNING | `Directory is empty` |
| Snapshot / CIM cache | otherwise | OK | `OK` |
| Output directory | exists, not a directory | ERROR | `Not a directory` |
| Output directory | exists, not writable | ERROR | `Directory is not writable` |
| Output directory | exists and writable | WARNING | `Directory exists` |
| Output directory | parent missing | ERROR | `Parent directory does not exist` |
| Output directory | does not exist, parent writable | WARNING | `Will be created` |

`Directory exists` is a WARNING rather than OK deliberately — it matches the mock-up and
signals that existing output may be overwritten. Warnings never block conversion; only
ERROR does.

**Extension point for phase 2:** `validateRequest` gains an optional sequence of extra
checker callables. Domain validation is added there, not in the UI.

### 4.4 Result types (`core/result.py`)

```python
@dataclass(frozen=True, slots=True)
class LogRecord:
    timestamp: datetime
    level: MessageLevel
    message: str

@dataclass(frozen=True, slots=True)
class StageUpdate:
    stage: ProcessingStage
    state: StageState

@dataclass(frozen=True, slots=True)
class ConversionOutcome:
    outputDirectory: Path
    excelFileCount: int
    detectedLines: int
    detectedSubstations: int
    finishedAt: datetime
```

`ConversionOutcome` is the contract the backend will fill. Nothing in this phase constructs
one outside tests and the opt-in demo service.

### 4.5 Session information (`core/session.py`)

```python
@dataclass(frozen=True, slots=True)
class SessionInfo:
    sessionId: str      # "%Y-%m-%d_%H%M" at application start
    user: str           # getpass.getuser(), "unknown" on failure
    computer: str       # platform.node(), "unknown" when empty
    pythonVersion: str  # platform.python_version()
    pysideVersion: str  # PySide6.__version__, injected so core stays Qt-free

    @classmethod
    def capture(cls, pysideVersion: str, now: datetime | None = None) -> SessionInfo: ...
```

`pysideVersion` is injected rather than imported, preserving the no-Qt rule in `core/`.

### 4.6 State machine and button matrix (`core/transitions.py`)

```python
class Trigger(Enum):
    PATH_CHANGED, VALIDATE_REQUESTED, VALIDATION_PASSED, VALIDATION_FAILED,
    START_REQUESTED, STOP_REQUESTED, CONVERSION_SUCCEEDED,
    CONVERSION_FAILED, CONVERSION_CANCELLED

def nextState(current: ApplicationState, trigger: Trigger) -> ApplicationState: ...
```

| From | Trigger | To |
| --- | --- | --- |
| IDLE / READY / SUCCEEDED / FAILED | VALIDATE_REQUESTED | VALIDATING |
| VALIDATING | VALIDATION_PASSED | READY |
| VALIDATING | VALIDATION_FAILED | IDLE |
| READY / SUCCEEDED / FAILED | START_REQUESTED | RUNNING |
| RUNNING | STOP_REQUESTED | STOPPING |
| RUNNING | CONVERSION_SUCCEEDED | SUCCEEDED |
| RUNNING | CONVERSION_FAILED | FAILED |
| RUNNING / STOPPING | CONVERSION_CANCELLED | IDLE |
| IDLE / READY / VALIDATING / SUCCEEDED / FAILED | PATH_CHANGED | IDLE |
| RUNNING / STOPPING | PATH_CHANGED | unchanged (inputs are locked) |

Any transition not in the table raises `InvalidTransitionError`. A path change invalidates
a prior validation, which is why it returns to IDLE — `READY` always means "these exact
four paths were validated".

Button enablement is one pure function, and is the **only** source of enabled state:

```python
@dataclass(frozen=True, slots=True)
class ButtonStates:
    preferences: bool
    validate: bool
    start: bool
    stop: bool
    exit: bool
    openOutputFolder: bool

def buttonStatesFor(state, hasAllPaths, outputDirectoryExists) -> ButtonStates: ...
```

| State | Preferences | Validate | Start | Stop | Exit | Open output |
| --- | --- | --- | --- | --- | --- | --- |
| IDLE | ✓ | if all paths | ✗ | ✗ | ✓ | if output dir exists |
| VALIDATING | ✓ | ✗ | ✗ | ✗ | ✓ | if output dir exists |
| READY | ✓ | ✓ | ✓ | ✗ | ✓ | if output dir exists |
| RUNNING | ✓ | ✗ | ✗ | ✓ | ✗ | if output dir exists |
| STOPPING | ✓ | ✗ | ✗ | ✗ | ✗ | if output dir exists |
| SUCCEEDED | ✓ | ✓ | ✓ | ✗ | ✓ | if output dir exists |
| FAILED | ✓ | ✓ | ✓ | ✗ | ✓ | if output dir exists |

`ActionBar.applyButtonStates(states)` is the single place `setEnabled` is called on action
buttons. Path selectors and Browse buttons are disabled as a group during RUNNING/STOPPING.

### 4.7 Preferences and QSettings (`core/settings.py`)

```python
@dataclass(frozen=True, slots=True)
class Preferences:
    rememberPaths: bool = True
    verboseLogging: bool = False
    maxLogRows: int = 5000          # 100 .. 100_000
    confirmOnExit: bool = True
    openOutputWhenFinished: bool = False
```

`SettingsStore` wraps a `QSettings` instance **passed into its constructor**, so tests
inject a temp-scoped store rather than touching the developer's real registry.

Organisation `MJAP`, application `CGMES MJAP Interface`. Persisted keys:
`paths/profileZip`, `paths/snapshotDataset`, `paths/cimCacheDataset`, `paths/outputDirectory`,
`window/geometry`, `window/state`, and one key per `Preferences` field. Unreadable or
out-of-range values fall back to defaults rather than raising. Paths are only restored when
`rememberPaths` is true; a restored path that no longer exists is cleared and logged.

---

## 5. Backend seam (`services/`)

```python
class CancellationToken:
    def cancel(self) -> None: ...
    @property
    def isCancelled(self) -> bool: ...      # thread-safe flag
    def raiseIfCancelled(self) -> None: ... # raises ConversionCancelled

class ProgressSink(Protocol):
    def stage(self, stage: ProcessingStage, state: StageState) -> None: ...
    def progress(self, percentage: int) -> None: ...
    def status(self, text: str) -> None: ...
    def log(self, level: MessageLevel, message: str) -> None: ...

class ConversionService(Protocol):
    def convert(self, request: ConversionRequest, sink: ProgressSink,
                token: CancellationToken) -> ConversionOutcome: ...
```

`ProgressSink` is a Protocol so the service never imports Qt. The controller supplies a
`SignalProgressSink` adapter that forwards each call onto a worker signal.

**`UnimplementedConversionService`** is the default wired into the application:

```python
def convert(self, request, sink, token) -> ConversionOutcome:
    raise NotImplementedError(
        "CGMES/CIMLA backend integration has not been implemented yet."
    )
```

Pressing Start therefore drives the real thread, the real state transitions and the real
error path, landing in FAILED with that message in the Errors tab. This is intentional: the
whole mechanism is exercised without a line of fabricated domain behaviour.

**`DemoConversionService`** exists for UI development only. It is reachable exclusively via
`--demo` on the command line, its first emitted log line is
`DEMO MODE — no conversion is performed and no files are written`, and it writes nothing to
disk. It lives in its own module so it cannot be reached by accident.

Phase 2 adds `CimlaConversionService` implementing the same Protocol. No GUI, controller or
core module changes.

---

## 6. Controller and threading

### 6.1 `ConversionWorker(QObject)` — runs inside the `QThread`

```python
class ConversionWorker(QObject):
    progressChanged = Signal(int)
    statusChanged = Signal(str)
    stageChanged = Signal(object)      # StageUpdate
    messageLogged = Signal(object)     # LogRecord
    completed = Signal(object)         # ConversionOutcome
    failed = Signal(str)
    cancelled = Signal()
    finished = Signal()                # always last, for thread teardown

    @Slot()
    def run(self) -> None: ...
```

`run` calls `self._service.convert(...)` and translates the result:
`ConversionOutcome` → `completed`; `ConversionCancelled` → `cancelled`; any other
`Exception` → `failed(str(exc))` with the traceback logged at ERROR. `finished` is emitted
in a `finally` block without exception, so the thread always tears down.

The worker catches broad `Exception` deliberately and only at this one boundary — an
uncaught exception on a `QThread` terminates the process. It is never swallowed: it is
logged with its traceback and surfaced in the UI. No bare `except:` and no `except: pass`
appears anywhere in the codebase.

**Deviation from the original brief, accepted:** `warningMessage` and `errorMessage` are not
separate signals. One `messageLogged(LogRecord)` carries a `MessageLevel`, and the Messages
card routes on it. Three parallel signals meant three connections that could drift apart.

### 6.2 `ConversionController(QObject)`

Owns the `ConversionRequest`, the `ApplicationState`, the service, the `QThread` and the
`CancellationToken`. Never imports or touches a widget.

```python
class ConversionController(QObject):
    stateChanged = Signal(object)              # ApplicationState
    requestChanged = Signal(object)            # ConversionRequest
    validationCompleted = Signal(object)       # ValidationReport
    stageChanged = Signal(object)              # StageUpdate
    progressChanged = Signal(int)
    statusChanged = Signal(str)
    messageLogged = Signal(object)             # LogRecord
    outcomeReady = Signal(object)              # ConversionOutcome
    buttonStatesChanged = Signal(object)       # ButtonStates

    def setPath(self, role: InputRole, path: Path | None) -> None: ...
    def validateInputs(self) -> None: ...
    def startConversion(self) -> None: ...
    def stopConversion(self) -> None: ...
    def openOutputFolder(self) -> None: ...
    def shutdown(self) -> None: ...
```

`stopConversion` sets the token and moves to STOPPING. Cancellation is **cooperative only**;
`QThread.terminate()` is never called. The service is expected to poll the token between
stages. `shutdown` requests cancellation and waits on the thread with a bounded timeout.

Thread lifecycle: worker `moveToThread`, `thread.started → worker.run`,
`worker.finished → thread.quit`, `thread.finished → deleteLater` on both. Signals cross the
thread boundary as queued connections, so all payloads are immutable frozen dataclasses.

`MainWindow.closeEvent` during RUNNING or STOPPING asks for confirmation, then calls
`shutdown()` and waits before accepting.

---

## 7. Presentation

### 7.1 Widget tree

```
MainWindow
└ QScrollArea                                    keeps the window usable when shrunk
  ├ HeaderBanner                                 gradient, logo, title, subtitle, circuit motif
  ├ QGridLayout (column stretch 7 : 3)
  │ ├ (0,0) InputSourcesCard        badge ①      4 × PathSelectorRow + ValidationStrip
  │ ├ (1,0) ProcessingCard          badge ②      StageStepper + QProgressBar + status line
  │ ├ (2,0) MessagesCard            badge ③      Log / Warnings (n) / Errors (n) + Clear
  │ ├ (0,1) OutputCard              badge ④      4 × KeyValueRow + Open Output Folder
  │ └ (1,1) SessionInfoCard                      5 × KeyValueRow
  └ ActionBar          Preferences │ Validate Inputs │ Start Conversion │ Stop │ Exit
```

Default window 1440 × 980, minimum 1120 × 760, geometry restored from `QSettings`. The left
column has a minimum width of 720 px; below that the grid collapses to a single column so
narrow displays remain usable. `MessagesCard` takes the vertical stretch.

### 7.2 Component behaviour

**`PathSelectorRow`** — icon, label, `QLineEdit`, `Browse…`. Configured with a role, a
dialog kind (open file / existing directory) and a filter. Opening its own `QFileDialog` is
UI behaviour and stays here; judging the result is not, and does not. Emits
`pathChanged(InputRole, object)`. The line edit is editable so a path can be pasted or
typed; edits are debounced and emit the same signal. Displays an elided path with the full
path as tooltip.

**`ValidationStrip`** — `applyReport(ValidationReport)` renders the verdict pill (green
check / amber / red) plus a two-column grid of per-check rows with status icons. `clear()`
returns it to the neutral pre-validation state.

**`StageStepper`** — custom `paintEvent`. Six nodes with connectors and labels beneath.
PENDING is a grey ring with a grey label; ACTIVE is an animated blue arc with a blue label;
COMPLETED is a filled green disc with a check and a dark label; FAILED is a red disc with a
cross. Connectors take the colour of the earlier node. A `QTimer` drives the ACTIVE arc at
~16 fps and is stopped whenever no stage is active, so an idle window costs no CPU.

The mock-up shows two highlighted nodes (an animated ring on *Extract Lines* and a solid
blue dot on *Classify Substations*). **Exactly one stage is ACTIVE at a time.** The solid
blue node is rendered as the immediate-next PENDING stage, which keeps the mock-up's
two-tone look without an ambiguous double-active state.

API: `setStageState(stage, state)`, `applyUpdate(StageUpdate)`, `reset()`.

**`MessagesCard`** — a `QAbstractTableModel` (`MessageLogModel`) of `LogRecord`s with three
`QSortFilterProxyModel` views: all / WARNING only / ERROR only. Tab labels carry live
counts. Capped by `Preferences.maxLogRows` as a ring buffer, dropping oldest first. Columns:
timestamp (tabular figures), level icon, message. `Clear` empties the model and resets the
counts. Auto-scrolls to the newest row only when already scrolled to the bottom, so reading
back through history is not interrupted.

**`OutputCard`** — `setExcelFileCount`, `setDetectedLines`, `setDetectedSubstations`,
`setLastRun`, and `clear()`. **Every value shows `—` until a real outcome sets it.** Numbers
are thousands-separated. `applyOutcome(ConversionOutcome)` sets all four at once.

**`SessionInfoCard`** — `applySessionInfo(SessionInfo)`. Static for the session's lifetime.

**`ActionBar`** — five buttons emitting `preferencesRequested`, `validateRequested`,
`startRequested`, `stopRequested`, `exitRequested`. `applyButtonStates(ButtonStates)` is its
only enablement path.

**`PreferencesDialog`** — edits a `Preferences` value and returns a new one; it does not
write settings itself. Fields: remember last used paths, verbose logging, max log rows
(spin box, 100–100 000), confirm before exit, open output folder when finished, plus
*Restore defaults*. OK / Cancel.

### 7.3 Visual design tokens (`resources/tokens.py`)

Taken from the mock-up. `theme.qss` is a template formatted from these values at load time,
because QSS has no variables — so painted widgets and stylesheet share one palette.

| Token | Value |
| --- | --- |
| `appBackground` | `#F2F5F9` |
| `cardBackground` | `#FFFFFF` |
| `cardBorder` | `#DCE4ED` |
| `headerGradientStart` / `End` | `#EAF3FD` / `#D7E9FA` |
| `primary` / `Hover` / `Pressed` | `#1668C7` / `#1257A8` / `#0E4586` |
| `titleNavy` | `#10375E` |
| `subtitle` | `#4E7CA8` |
| `textPrimary` / `Secondary` / `Muted` | `#1F2933` / `#6B7684` / `#98A2AE` |
| `success` / background / border | `#21A366` / `#EBF8F1` / `#BFE6D2` |
| `warning` | `#E9A21A` |
| `error` | `#E0433F` |
| `track` | `#E4E9F0` |
| `stepperPending` | `#C7D0DA` |
| Card radius / control radius | 10 px / 6 px |
| Card padding / grid gap | 16 px / 12 px |

Typography: Segoe UI with a documented fallback chain. Title 28 px semibold, subtitle 13 px,
card title 15 px semibold, body 13 px, timestamps in a monospace fallback for column
alignment. High-DPI uses `PassThrough` rounding so 125 % and 150 % scaling stay crisp.

Icons are approximately 19 hand-authored SVGs under `resources/icons/`: app logo, zip,
database, folder, folder-open, check-circle, warning-triangle, error-circle, info, excel,
lines, substation, clock, gear, check-shield, play, stop, exit, trash. Nothing is fetched at
runtime and no external asset is referenced.

### 7.4 GUI-level logging

The application logs its own events, and only its own: application started, settings
restored, each path selection, validation requested and its verdict, start requested, stop
requested, output folder opened, preferences changed. Domain-processing messages arrive from
the backend in phase 2. No log line in this phase implies that CGMES processing occurred.

---

## 8. Testing

`pytest` + `pytest-qt`, with `QT_QPA_PLATFORM=offscreen` so the suite runs headless on the
Linux CI agent. Existing tests are untouched; new tests live under `tests/gui/`.

**Without Qt** — `validateRequest` for every row of the rules table; `nextState` for every
legal transition and a rejection for illegal ones; `buttonStatesFor` for all seven states;
`SessionInfo.capture`; `Preferences` clamping and defaults.

**With `qtbot`** — `SettingsStore` round-trip against a temp-scoped `QSettings`;
`PathSelectorRow` emits `pathChanged`; `ValidationStrip` renders each `CheckStatus`;
`StageStepper` state application and timer stopping when idle; `MessagesCard` filtering,
live counts, ring-buffer cap and clear; `OutputCard` shows `—` before any outcome and
formats numbers after; `ActionBar` enablement driven from the matrix; `PreferencesDialog`
returns an edited value.

**Controller** — with a `FakeConversionService`: IDLE → VALIDATING → READY → RUNNING →
SUCCEEDED with signals in order; a raising service yields FAILED with the message; a service
polling the token yields STOPPING → IDLE on cancel; the thread is joined after each run;
`UnimplementedConversionService` surfaces as FAILED carrying the NotImplementedError text.

**Packaging** — `version.py.__version__` equals the version in `pyproject.toml`.

---

## 9. Packaging and release automation

### 9.1 Local build scripts

`scripts/build.ps1` (Windows) and `scripts/build.sh` (Linux/macOS) run the identical
sequence, so a local build and a pipeline build are the same build:

```
uv sync --extra gui --group dev
uv run ruff check .
uv run pytest                      QT_QPA_PLATFORM=offscreen
uv run pyinstaller packaging/cgmesmjap.spec
sha256  ->  dist/CGMES-MJAP-Interface-<version>.exe.sha256
```

`build.sh` produces a native binary and states plainly that a Windows `.exe` requires a
Windows host — it does not pretend to cross-compile.

`packaging/cgmesmjap.spec` builds one-file, windowed (no console), with an `.ico` and the
`resources/` tree bundled. One-file is chosen over one-dir because the artifact is committed
to the repository, where a single file is far easier to manage.

`scripts/release.ps1` and `scripts/release.sh` bump `version.py` and `pyproject.toml`
together, commit, tag `v<version>` and push. Pushing the tag is what starts a release.

### 9.2 `azure-pipelines.yml`

Two stages, Microsoft-hosted agents.

**Stage `Verify`** — `ubuntu-latest`, on every push to `main`, every PR and every `v*` tag.
Installs uv, `uv sync --extra gui --group dev`, `ruff check`, `pytest` with
`QT_QPA_PLATFORM=offscreen`, publishes JUnit results.

**Stage `Package`** — `windows-latest`, `dependsOn: Verify`, gated on
`startsWith(variables['Build.SourceBranch'], 'refs/tags/v')`. It:

1. checks out with `persistCredentials: true`
2. asserts the tag matches `version.py.__version__`, failing the build on mismatch
3. runs `scripts/build.ps1`
4. publishes the exe and its `.sha256` as a Pipeline Artifact
5. checks out `main` fresh (`git fetch origin main && git checkout -B main origin/main`),
   copies the artifact into `releases/`, commits and pushes

Step 5 is required because a tag build starts in detached HEAD and cannot push directly.
The release commit message ends with `[skip ci]`, and the CI trigger excludes `releases/**`
— two independent guards against the pipeline retriggering itself.

**Prerequisite, to be configured once in Azure DevOps:** the project's Build Service
identity needs *Contribute* permission on the repository. Without it step 5 fails with a
403. This is a manual, one-time setup step and is documented in the README.

`.gitignore` continues to ignore `dist/` and `build/`; `releases/` is tracked.

---

## 10. Project configuration

`pyproject.toml` gains:

- `[project.optional-dependencies] gui = ["PySide6>=6.7"]`
- dev group adds `pytest-qt`, `ruff`, `pyinstaller`
- `[project.gui-scripts] cgmes-mjap = "cgmesmjap.app:main"` — a Windows GUI entry point that
  launches without a console window
- `[tool.ruff]` selecting `E, F, I, UP, B` and **not** `N`, so the repository's camelCase
  convention passes cleanly; line length 110

---

## 11. Acceptance criteria

1. `uv run cgmes-mjap` opens a window that visually matches the mock-up.
2. All four selectors browse, persist to `QSettings`, and restore on next launch.
3. *Validate Inputs* runs the filesystem checks and renders the strip, including amber
   `Directory exists` for an existing output directory.
4. *Start Conversion* runs the real worker thread and ends in FAILED with
   `CGMES/CIMLA backend integration has not been implemented yet.` in the Errors tab.
5. *Stop* transitions RUNNING → STOPPING → IDLE cooperatively, never via `terminate()`.
6. *Open Output Folder* opens the configured directory, and is disabled when there is none.
7. The Output card shows `—` for all four values until a real outcome arrives.
8. Every button's enabled state comes from `buttonStatesFor`, verified by test.
9. Closing during a run prompts, cancels and joins the thread.
10. `ruff check` and `pytest` both pass; no Qt import exists anywhere under `core/`.
11. `build.ps1` produces a runnable exe on Windows; a `v*` tag lands it in `releases/`.

---

## 12. Deferred to phase 2

To be defined when the conversion source code is supplied: what Start invokes, how CGMES
models are loaded, how CIMLA is called, how progress is computed, how the six UI stages map
onto real operations, how cancellation is honoured inside the backend, which warnings and
errors are produced, how results are represented, how Excel output is written, which backend
exceptions need handling, and which validation rules are domain-specific.

None of these require a GUI change. They are implemented behind `ConversionService`.
