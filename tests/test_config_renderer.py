import os
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "kubernetes/bin/render-nr-ue-config.py"


@pytest.fixture
def renderer_env(tmp_path):
    template = tmp_path / "nr-ue.conf.tmpl"
    template.write_text(
        'uicc0 = { imsi = "${imsi}"; imei = "$imei"; key = "$key"; opc = "$opc"; };\n'
        'plmn = { mcc = "$mcc"; mnc = "${mnc}"; };\n'
        'sessions = ({ dnn = "ims"; }); // literal $$\n'
    )
    return {
        **os.environ,
        "imsi": "001010000000100", "imei": "356938035643803",
        "key": "00112233445566778899aabbccddeeff",
        "opc": "63bfa50ee6523365ff14c1f45f88737d",
        "mcc": "001", "mnc": "01",
        "templatePath": str(template),
        "outputPath": str(tmp_path / "generated/nr-ue.conf"),
    }


def run_renderer(env):
    return subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True)


def test_renders_full_config(renderer_env):
    result = run_renderer(renderer_env)
    assert result.returncode == 0, result.stderr
    assert Path(renderer_env["outputPath"]).read_text() == (
        'uicc0 = { imsi = "001010000000100"; imei = "356938035643803"; '
        'key = "00112233445566778899aabbccddeeff"; opc = "63bfa50ee6523365ff14c1f45f88737d"; };\n'
        'plmn = { mcc = "001"; mnc = "01"; };\n'
        'sessions = ({ dnn = "ims"; }); // literal $\n'
    )


@pytest.mark.parametrize("failure", ["missing", "empty", "unknown", "invalid", "unreadable"])
def test_failure_does_not_write_config(renderer_env, failure):
    if failure == "missing":
        del renderer_env["key"]
    elif failure == "empty":
        renderer_env["imsi"] = ""
    elif failure == "unreadable":
        Path(renderer_env["templatePath"]).unlink()
    else:
        Path(renderer_env["templatePath"]).write_text(
            "$key " + ("${unknown}" if failure == "unknown" else "${broken")
        )
    result = run_renderer(renderer_env)
    assert result.returncode != 0
    assert not Path(renderer_env["outputPath"]).exists()
    assert renderer_env["key"] not in result.stderr if "key" in renderer_env else True
