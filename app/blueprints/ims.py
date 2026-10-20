import json
import signal
import threading
from collections import deque

import click
from flask import Blueprint, current_app
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..ims.config import SipSettings
from ..ims.network import resolve_network
from ..ims.outbox import Outbox
from ..ims.pjsua import PjsuaTransport, load_binding
from ..services.messaging import record_received_message

ims = Blueprint('ims', __name__, cli_group='ims')


def handle_event(event, include_body=False):
    """Commit incoming text before logging success; never let DB errors cross SWIG."""
    event = dict(event)
    if event['type'] == 'incoming_message':
        media_type = event.get('content_type', '').split(';', 1)[0].strip().lower()
        if media_type != 'text/plain':
            event.update(status='unsupported_content_type', persisted=False)
            event.pop('body', None)
        else:
            try:
                message = record_received_message(event['sender'], event['recipient'], event['body'])
                event.update(status='received', persisted=True, message_id=message.id)
            except SQLAlchemyError:
                db.session.rollback()
                # SQLAlchemy exception strings may contain message text and credentials.
                event.update(status='persistence_failed', persisted=False)
            finally:
                db.session.remove()
    if not include_body:
        event.pop('body', None)
    click.echo(json.dumps(event))


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

    stopping = threading.Event()

    def stop(signum, frame):
        stopping.set()

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    transport = None
    try:
        db.create_all()
        if settings.interface:
            click.echo(json.dumps({'type': 'waiting_for_interface', 'interface': settings.interface}))
        settings = resolve_network(settings, stopping)
        if stopping.is_set():
            return
        events = deque()
        # Drain callbacks outside SWIG before doing database work.
        transport = PjsuaTransport(settings, events.append)
        outbox = Outbox(transport, settings.account_uri, lambda event: handle_event(event, include_body))
        outbox.recover()
        transport.start()
        click.echo(json.dumps({'type': 'listener_started', 'address': settings.bind_address, 'port': settings.port}))
        while not stopping.is_set():
            transport.poll()
            while events:
                event = events.popleft()
                if event['type'] == 'message_status':
                    outbox.handle_status(event)
                handle_event(event, include_body)
            if not stopping.is_set():
                outbox.tick()
    except RuntimeError as error:
        raise click.ClickException(str(error)) from error
    finally:
        try:
            if transport is not None:
                transport.close()
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
