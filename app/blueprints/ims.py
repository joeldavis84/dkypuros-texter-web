import json
import signal

import click
from flask import Blueprint, current_app

from ..ims.config import SipSettings
from ..ims.pjsua import PjsuaTransport, load_binding

ims = Blueprint('ims', __name__, cli_group='ims')


@ims.cli.command('check')
def check():
    """Validate settings and native imports without opening sockets."""
    try:
        SipSettings.from_config(current_app.config)
        load_binding()
    except (ValueError, RuntimeError) as error:
        raise click.ClickException(str(error)) from error
    click.echo('PJSUA2 import and configuration OK; connectivity was not tested.')


@ims.cli.command('listen')
@click.option('--include-body', is_flag=True, help='Include message content in stdout events.')
def listen(include_body):
    """Run one SIP event loop until SIGINT/SIGTERM; may register with the registrar."""
    try:
        settings = SipSettings.from_config(current_app.config)
    except ValueError as error:
        raise click.ClickException(str(error)) from error

    def emit(event):
        if not include_body:
            event = {key: value for key, value in event.items() if key != 'body'}
        click.echo(json.dumps(event))

    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    transport = PjsuaTransport(settings, emit)
    try:
        transport.start()
        while not stopping:
            transport.poll()
    except RuntimeError as error:
        raise click.ClickException(str(error)) from error
    finally:
        try:
            transport.close()
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
