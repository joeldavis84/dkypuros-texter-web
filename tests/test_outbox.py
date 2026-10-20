from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from app import create_app
from app.extensions import db
from app.ims.config import SipSettings
from app.ims.outbox import Outbox
from app.ims.pjsua import PjsuaTransport
from app.models import Message
from test_ims import fake_binding


@pytest.fixture
def app(tmp_path):
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(tmp_path / 'messages.db'),
                      'IMS_ACCOUNT_URI': 'sip:alice@test', 'IMS_INTERFACE': ''})
    with app.app_context():
        db.create_all()
    return app


def queue(app, body='Hello héllo 🌍'):
    response = app.test_client().post('/api/v1/messages', json={'recipient': 'sip:bob@test', 'body': body})
    assert response.status_code == 202
    return response.json['id']


def status(app, message_id):
    return app.test_client().get(f'/api/v1/messages/{message_id}').json['status']


def test_api_to_pjsua_and_out_of_order_responses(app):
    first, second = queue(app), queue(app, 'second to same recipient')
    pj = fake_binding()
    events = []
    transport = PjsuaTransport(SipSettings('sip:alice@test', proxy_uri='sip:192.168.27.57:5060;lr'), events.append, pj)
    transport.start()
    outbox = Outbox(transport, 'sip:alice@test', events.append)
    try:
        with app.app_context():
            outbox.recover()
            outbox.tick()
            outbox.next_scan = 0
            outbox.tick()
        params = [call.args[0] for call in pj.Buddy.return_value.sendInstantMessage.call_args_list]
        assert len(params) == 2
        assert params[0].content == 'Hello héllo 🌍'
        assert params[0].contentType == 'text/plain'
        assert transport.account.config.sipConfig.proxies == ['sip:192.168.27.57:5060;lr']
        assert status(app, first) == status(app, second) == 'sending'
        # Same recipient, reverse response order: correlate by token, not URI.
        for param, code in ((params[1], 404), (params[0], 202)):
            transport.account.onInstantMessageStatus(NS(userData=param.userData, toUri='sip:bob@test', code=code))
        with app.app_context():
            for event in events:
                outbox.handle_status(event)
        assert status(app, first) == 'sent'
        assert status(app, second) == 'failed'
        assert not transport.pending_messages
    finally:
        transport.close()


def test_unregistered_waits_then_sends_only_once(app):
    message_id = queue(app)
    transport = Mock(pending_messages={})
    transport.ready_to_send.return_value = False
    outbox = Outbox(transport, 'sip:alice@test', Mock())
    with app.app_context():
        outbox.tick()
    assert status(app, message_id) == 'queued'
    transport.send_text.assert_not_called()
    transport.ready_to_send.return_value = True
    with app.app_context():
        outbox.next_scan = 0
        outbox.tick()
        outbox.next_scan = 0
        outbox.tick()
    transport.send_text.assert_called_once_with('sip:bob@test', 'Hello héllo 🌍', message_id=message_id)
    assert status(app, message_id) == 'sending'


def test_send_exception_timeout_late_result_and_restart(app):
    first = queue(app)
    transport = Mock(pending_messages={})
    transport.ready_to_send.return_value = True
    transport.send_text.side_effect = RuntimeError('native send failed')
    outbox = Outbox(transport, 'sip:alice@test', Mock(), response_timeout=0)
    with app.app_context():
        outbox.tick()
    assert status(app, first) == 'failed'
    second = queue(app)
    transport.send_text.side_effect = None
    with app.app_context():
        outbox.next_scan = 0
        outbox.tick()
        outbox.tick()
    assert status(app, second) == 'unknown'
    assert transport.send_text.call_count == 2
    with app.app_context():
        outbox.handle_status({'message_id': second, 'code': 200})
    assert status(app, second) == 'sent'
    third = queue(app)
    with app.app_context():
        outbox.next_scan = 0
        outbox.tick()
        Outbox(transport, 'sip:alice@test', Mock()).recover()
    assert status(app, third) == 'unknown'
    assert transport.send_text.call_count == 3


def test_recovery_preserves_old_records_and_other_accounts(app):
    with app.app_context():
        for sender, state in [('sip:alice@test', 'simulated'), ('sip:alice@test', 'received'),
                              ('sip:other@test', 'sending')]:
            db.session.add(Message(sender=sender, recipient='sip:bob@test', body='existing', status=state))
        db.session.commit()
        Outbox(Mock(), 'sip:alice@test', Mock()).recover()
        assert [m.status for m in db.session.query(Message).order_by(Message.id)] == ['simulated', 'received', 'sending']


def test_sip_timeout_and_provisional_response(app):
    message_id = queue(app)
    outbox = Outbox(Mock(pending_messages={}), 'sip:alice@test', Mock())
    with app.app_context():
        outbox.tick()
        outbox.handle_status({'message_id': message_id, 'code': 100})
    assert status(app, message_id) == 'sending'
    with app.app_context():
        outbox.handle_status({'message_id': message_id, 'code': 408})
    assert status(app, message_id) == 'unknown'


def test_listener_loop_sends_and_persists_callback_results(app, monkeypatch):
    import signal
    outgoing_id = queue(app, 'loopback text')
    pj = fake_binding()
    monkeypatch.setattr('app.ims.pjsua.load_binding', lambda: pj)

    class LoopbackTransport(PjsuaTransport):
        def poll(self, timeout_ms=100):
            sends = pj.Buddy.return_value.sendInstantMessage.call_args_list
            if not sends:
                return  # First loop iteration will claim and send the queued row.
            param = sends[0].args[0]
            self.account.onInstantMessageStatus(NS(userData=param.userData, toUri='sip:bob@test', code=200))
            self.account.onInstantMessage(NS(fromUri='sip:alice@test', toUri='sip:bob@test',
                                            contentType='text/plain', msgBody=param.content))
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)

    monkeypatch.setattr('app.blueprints.ims.PjsuaTransport', LoopbackTransport)
    result = app.test_cli_runner().invoke(args=['ims', 'listen'])
    assert result.exit_code == 0, result.output
    assert 'loopback text' not in result.output
    assert status(app, outgoing_id) == 'sent'
    rows = app.test_client().get('/api/v1/messages').json['messages']
    assert len(rows) == 2
    assert rows[0]['status'] == 'received'
    assert rows[0]['body'] == 'loopback text'
    pj.Buddy.return_value.sendInstantMessage.assert_called_once()
    pj.Endpoint.return_value.libDestroy.assert_called_once()
