import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest


def wait_for_files(paths, process):
    deadline = time.monotonic() + 5
    while not all(path.exists() for path in paths):
        assert process.poll() is None, 'Supervisor stopped before children became ready'
        assert time.monotonic() < deadline, 'Children did not start'
        time.sleep(0.02)


@pytest.mark.parametrize('shutdown', ['signal', 'child_exit'])
def test_supervisor_starts_both_and_cleans_up(tmp_path, shutdown):
    children = []
    for index in range(2):
        ready = tmp_path / f'{index}.ready'
        stopped = tmp_path / f'{index}.stopped'
        script = (
            'import os, signal, time\n'
            'from pathlib import Path\n'
            'def stop(*args):\n'
            f'    Path({str(stopped)!r}).write_text("stopped")\n'
            '    raise SystemExit(0)\n'
            'signal.signal(signal.SIGTERM, stop)\n'
            f'Path({str(ready)!r}).write_text(str(os.getpid()))\n'
            'while True: time.sleep(0.01)\n'
        )
        children.append([sys.executable, '-c', script])
    driver = (
        'from app.runtime import run_processes\n'
        f'raise SystemExit(run_processes({children!r}, shutdown_timeout=2))\n'
    )
    process = subprocess.Popen([sys.executable, '-c', driver], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        ready = [tmp_path / f'{index}.ready' for index in range(2)]
        wait_for_files(ready, process)
        if shutdown == 'signal':
            process.send_signal(signal.SIGTERM)
        else:
            os.kill(int(ready[0].read_text()), signal.SIGTERM)
        process.communicate(timeout=5)
        assert process.returncode == (0 if shutdown == 'signal' else 1)
        assert all((tmp_path / f'{index}.stopped').exists() for index in range(2))
        for path in ready:
            with pytest.raises(ProcessLookupError):
                os.kill(int(path.read_text()), 0)
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=5)


def test_container_startup_initializes_shared_db_and_listener(monkeypatch, tmp_path):
    from app import runtime
    from unittest.mock import Mock
    for name in list(os.environ):
        if name.startswith('IMS_') or name in ('sipIdentity', 'sipDomain', 'imsInterface'):
            monkeypatch.delenv(name)
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'messages.db'))
    run = Mock(return_value=0)
    monkeypatch.setattr(runtime, 'run_processes', run)
    assert runtime.main() == 0
    assert len(run.call_args.args[0]) == 1
    monkeypatch.setenv('sipIdentity', 'user1')
    monkeypatch.setenv('sipDomain', 'dkypuros')
    assert runtime.main() == 0
    commands = run.call_args.args[0]
    assert len(commands) == 2
    assert commands[0][1:3] == ['-m', 'gunicorn']
    assert commands[1][-2:] == ['ims', 'listen']
    assert (tmp_path / 'messages.db').is_file()
