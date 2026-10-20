"""Container process supervisor for Gunicorn and one optional SIP listener."""
import os
import signal
import subprocess
import sys
import threading
import time


def run_processes(commands, shutdown_timeout=10):
    stopping = threading.Event()
    children = []
    previous = {
        sig: signal.signal(sig, lambda *_: stopping.set())
        for sig in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        for command in commands:
            if stopping.is_set():
                return 0
            children.append(subprocess.Popen(command, start_new_session=True))
        while not stopping.wait(0.1):
            for child in children:
                status = child.poll()
                if status is not None:
                    print('Application process exited; stopping container.', file=sys.stderr, flush=True)
                    # Even an unexpected clean exit should trigger a restart.
                    return status if status > 0 else 1
        return 0
    finally:
        for child in children:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + shutdown_timeout
        for child in children:
            try:
                child.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    from flask.cli import load_dotenv
    from . import create_app
    from .extensions import db

    # Match Flask CLI loading so both child processes inherit the same DB/SIP settings.
    load_dotenv()
    app = create_app()
    with app.app_context():
        db.create_all()
    commands = [[sys.executable, '-m', 'gunicorn', '--bind', '0.0.0.0:8080', 'wsgi:app']]
    if app.config['IMS_ACCOUNT_URI'] or app.config['IMS_INTERFACE']:
        commands.append([sys.executable, '-m', 'flask', '--app', 'app', 'ims', 'listen'])
    return run_processes(commands)


if __name__ == '__main__':
    sys.exit(main())
