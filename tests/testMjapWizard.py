"""Full parser -> unchanged MJAP wizard -> QGIS project, in isolated processes."""
import json
import subprocess
import sys
from pathlib import Path
import pytest

pytest.importorskip('qgis.core')


@pytest.mark.parametrize('scenario', ['populated', 'closed-lifetimes', 'line-and-transformer'])
def testFullWizardHasValidLayersJoinsStylesAndNoErrorMessages(tmp_path, scenario):
    result = subprocess.run([sys.executable, '-X', 'faulthandler',
                             str(Path(__file__).with_name('mjapWizardProbe.py')),
                             str(tmp_path), scenario], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((tmp_path / 'report.json').read_text())
    assert report['expression_errors'] == []
    assert not [message for message in report['messages'] if message[0] in ('warning', 'critical')]
    # Only pandas' diagnostic about inferring all-missing ABN text is accepted.
    # No dtype FutureWarning is allowed: the parser keeps the column textual.
    assert all(warning.startswith('Could not infer format,') for warning in report['warnings'])
    if scenario == 'closed-lifetimes': assert report['warnings'] == []
