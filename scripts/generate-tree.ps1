$path = Read-Host 'Enter destination path'
$name = Read-Host 'Enter project name'

$folders = @(
    'docs'
    'docs/superpowers'
    'docs/superpowers/specs'
    'packaging'
    'scripts'
    'src'
    'src/cgmesparser'
    'src/cgmesparser/gui'
    'src/cgmesparser/gui/controller'
    'src/cgmesparser/gui/core'
    'src/cgmesparser/gui/dialogs'
    'src/cgmesparser/gui/resources'
    'src/cgmesparser/gui/services'
    'src/cgmesparser/gui/widgets'
    'tests'
)

$files = @(
    'packaging/makeIcon.py'
    'src/cgmesparser/__init__.py'
    'src/cgmesparser/gui/__init__.py'
    'src/cgmesparser/gui/__main__.py'
    'src/cgmesparser/gui/app.py'
    'src/cgmesparser/gui/controller/__init__.py'
    'src/cgmesparser/gui/controller/conversion.py'
    'src/cgmesparser/gui/controller/worker.py'
    'src/cgmesparser/gui/core/__init__.py'
    'src/cgmesparser/gui/core/request.py'
    'src/cgmesparser/gui/core/result.py'
    'src/cgmesparser/gui/core/session.py'
    'src/cgmesparser/gui/core/settings.py'
    'src/cgmesparser/gui/core/states.py'
    'src/cgmesparser/gui/core/transitions.py'
    'src/cgmesparser/gui/core/validation.py'
    'src/cgmesparser/gui/dialogs/__init__.py'
    'src/cgmesparser/gui/dialogs/preferences.py'
    'src/cgmesparser/gui/mainWindow.py'
    'src/cgmesparser/gui/resources/__init__.py'
    'src/cgmesparser/gui/resources/icons.py'
    'src/cgmesparser/gui/resources/theme.py'
    'src/cgmesparser/gui/resources/tokens.py'
    'src/cgmesparser/gui/services/__init__.py'
    'src/cgmesparser/gui/services/demo.py'
    'src/cgmesparser/gui/services/protocol.py'
    'src/cgmesparser/gui/services/unimplemented.py'
    'src/cgmesparser/gui/settingsStore.py'
    'src/cgmesparser/gui/version.py'
    'src/cgmesparser/gui/widgets/__init__.py'
    'src/cgmesparser/gui/widgets/actionBar.py'
    'src/cgmesparser/gui/widgets/common.py'
    'src/cgmesparser/gui/widgets/header.py'
    'src/cgmesparser/gui/widgets/inputSources.py'
    'src/cgmesparser/gui/widgets/messages.py'
    'src/cgmesparser/gui/widgets/output.py'
    'src/cgmesparser/gui/widgets/processing.py'
    'src/cgmesparser/gui/widgets/session.py'
    'tests/conftest.py'
    'tests/testController.py'
    'tests/testCore.py'
    'tests/testMainWindow.py'
    'tests/testServices.py'
    'tests/testSettingsStore.py'
    'tests/testTransitions.py'
    'tests/testValidation.py'
    'tests/testWidgets.py'
)

$root = Join-Path $path $name
New-Item -ItemType Directory -Path $root -Force | Out-Null

foreach ($folder in $folders) {
    New-Item -ItemType Directory -Path (Join-Path $root $folder) -Force | Out-Null
}

foreach ($file in $files) {
    $filePath = Join-Path $root $file
    if (-not (Test-Path -LiteralPath $filePath)) {
        New-Item -ItemType File -Path $filePath | Out-Null
    }
}

Write-Host "Created $name with $($folders.Count) folders and $($files.Count) Python files in $path"
