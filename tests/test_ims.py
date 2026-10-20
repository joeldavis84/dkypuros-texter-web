from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from app import create_app
from app.ims.config import SipSettings
from app.ims.pjsua import PjsuaTransport


def fake_binding():
    class Account:
        def create(self, config): self.config = config
        def getInfo(self): return NS(regIsActive=True)
        def shutdown(self): self.stopped = True
    pj = NS(Account=Account, PJSIP_TRANSPORT_TCP=1, PJSIP_TRANSPORT_UDP=2)
    endpoint = Mock()
    pj.Endpoint = Mock(return_value=endpoint)
    pj.EpConfig = lambda: NS(uaConfig=NS(), logConfig=NS())
    pj.TransportConfig = NS
    pj.AccountConfig = lambda: NS(regConfig=NS(), sipConfig=NS(proxies=[], authCreds=[]))
    pj.BuddyConfig = NS
    pj.Buddy = Mock()
    pj.SendInstantMessageParam = NS
    pj.AuthCredInfo = Mock()
    return pj


def test_lifecycle_callbacks_and_send():
    pj = fake_binding()
    events = []
    transport = PjsuaTransport(SipSettings('sip:a@test', registrar_uri='sip:test'), events.append, pj)
    transport.start()
    transport.poll()
    transport.send_text('sip:b@test', 'hello')
    params = pj.Buddy.return_value.sendInstantMessage.call_args.args[0]
    assert params.content == 'hello'
    assert params.contentType == 'text/plain'
    transport.account.onInstantMessage(NS(fromUri='sip:b@test', toUri='sip:a@test', contentType='text/plain', msgBody='reply'))
    assert events[0]['body'] == 'reply'
    transport.account.onInstantMessageStatus(NS(toUri='sip:b@test', code=202))
    assert events[1]['code'] == 202
    transport.account.onRegState(NS(code=200))
    assert events[2]['active'] is True
    account = transport.account
    transport.close()
    transport.close()
    assert account.stopped
    pj.Endpoint.return_value.libDestroy.assert_called_once()
    with pytest.raises(RuntimeError):
        transport.send_text('sip:b@test', 'hello')


def test_startup_failure_destroys_endpoint():
    pj = fake_binding()
    pj.Endpoint.return_value.libInit.side_effect = RuntimeError('failed')
    transport = PjsuaTransport(SipSettings('sip:a@test'), lambda event: None, pj)
    with pytest.raises(RuntimeError, match='failed'):
        transport.start()
    pj.Endpoint.return_value.libDestroy.assert_called_once()


def test_missing_binding_does_not_break_flask(monkeypatch):
    app = create_app({'TESTING': True, 'IMS_ACCOUNT_URI': 'sip:a@test'})
    assert app.test_client().get('/api/v1/health').status_code == 200
    monkeypatch.setattr('app.ims.pjsua.importlib.import_module', Mock(side_effect=ImportError))
    result = app.test_cli_runner().invoke(args=['ims', 'check'])
    assert result.exit_code == 1
    assert 'native Python binding is unavailable' in result.output


@pytest.mark.parametrize('key,value', [('IMS_TRANSPORT', 'tls'), ('IMS_PORT', -1), ('IMS_ACCOUNT_URI', ''), ('IMS_BIND_ADDRESS', 'remote-host'), ('IMS_PASSWORD', 'secret')])
def test_invalid_settings(key, value):
    app = create_app({'IMS_ACCOUNT_URI': 'sip:a@test', key: value})
    with pytest.raises(ValueError):
        SipSettings.from_config(app.config)


def test_credentials_not_in_repr():
    assert 'topsecret' not in repr(SipSettings('sip:a@test', password='topsecret'))


def test_deployment_environment_and_overrides():
    from app.ims.config import environment_config
    env = {'sipIdentity': 'user1', 'sipDomain': 'dkypuros', 'sipServer': '192.168.27.57',
           'sipPort': '5060', 'imsInterface': 'oaitun_ue1p2'}
    settings = SipSettings.from_config(environment_config(env))
    assert settings.account_uri == 'sip:user1@dkypuros'
    assert settings.registrar_uri == 'sip:dkypuros'
    assert settings.proxy_uri == 'sip:192.168.27.57:5060;lr'
    assert settings.interface == 'oaitun_ue1p2'
    assert settings.port == 5062
    env.update(IMS_ACCOUNT_URI='sip:override@test', IMS_REGISTRAR_URI='', IMS_PORT='5090',
               IMS_BIND_ADDRESS='127.0.0.1')
    settings = SipSettings.from_config(environment_config(env))
    assert settings.account_uri == 'sip:override@test'
    assert settings.registrar_uri == ''
    assert settings.port == 5090
    assert settings.bind_address == '127.0.0.1'


def test_interface_wait_and_advertised_address(monkeypatch):
    from app.ims.network import resolve_network
    addresses = Mock(side_effect=[None, '10.0.0.2'])
    monkeypatch.setattr('app.ims.network.interface_address', addresses)
    stopped = Mock()
    stopped.is_set.return_value = False
    settings = resolve_network(SipSettings('sip:a@test', interface='ue1'), stopped)
    stopped.wait.assert_called_once_with(1)
    assert settings.bind_address == settings.public_address == '10.0.0.2'
    pj = fake_binding()
    transport = PjsuaTransport(settings, lambda event: None, pj)
    transport.start()
    cfg = pj.Endpoint.return_value.transportCreate.call_args.args[1]
    assert cfg.boundAddress == cfg.publicAddress == '10.0.0.2'
    assert cfg.port == 5062
    transport.close()


def test_interface_missing_timeout_and_cancellation(monkeypatch):
    import threading
    from app.ims.network import resolve_network
    monkeypatch.setattr('app.ims.network.interface_address', Mock(return_value=None))
    settings = SipSettings('sip:a@test', interface='ue1')
    stopped = threading.Event()
    with pytest.raises(RuntimeError, match='Timed out'):
        resolve_network(settings, stopped, timeout=0)
    stopped.set()
    resolve_network(settings, stopped)


def test_interface_address_inspection(monkeypatch):
    from app.ims.network import interface_address
    run = Mock(return_value=NS(returncode=0, stdout='[{"addr_info": [{"family": "inet", "local": "10.0.0.2"}]}]'))
    monkeypatch.setattr('app.ims.network.subprocess.run', run)
    assert interface_address('ue1') == '10.0.0.2'
    assert run.call_args.args[0] == ['ip', '-j', '-4', 'addr', 'show', 'dev', 'ue1']
    run.return_value = NS(returncode=1)
    assert interface_address('ue1') is None


def test_listener_callback_saved_and_visible_to_web(monkeypatch, tmp_path):
    import json
    import signal
    database = 'sqlite:///' + str(tmp_path / 'shared.db')
    config = {'TESTING': True, 'SQLALCHEMY_DATABASE_URI': database,
              'IMS_ACCOUNT_URI': 'sip:a@test', 'IMS_INTERFACE': ''}
    listener = create_app(config)
    web = create_app(config)
    pj = fake_binding()
    monkeypatch.setattr('app.ims.pjsua.load_binding', lambda: pj)
    transports = []

    class TestTransport(PjsuaTransport):
        def start(self):
            super().start()
            transports.append(self)

        def poll(self, timeout_ms=100):
            self.account.onInstantMessage(NS(
                fromUri='sip:b@test', toUri='sip:a@test', contentType='text/plain; charset=utf-8',
                msgBody='Incoming text: héllo',
            ))
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)

    monkeypatch.setattr('app.blueprints.ims.PjsuaTransport', TestTransport)
    result = listener.test_cli_runner().invoke(args=['ims', 'listen'])
    assert result.exit_code == 0, result.output
    assert 'Incoming text' not in result.output
    events = [json.loads(line) for line in result.output.splitlines()]
    incoming = next(event for event in events if event['type'] == 'incoming_message')
    assert incoming['persisted'] is True
    assert incoming['status'] == 'received'
    messages = web.test_client().get('/api/v1/messages').json['messages']
    assert len(messages) == 1
    message = messages[0]
    assert message['id'] == incoming['message_id']
    assert message['status'] == 'received'
    assert message['sender'] == 'sip:b@test'
    assert message['recipient'] == 'sip:a@test'
    assert message['body'] == 'Incoming text: héllo'
    assert message['created_at']
    assert web.test_client().get('/api/v1/messages/' + str(message['id'])).json == message
    assert transports[0].endpoint is None
    simulated = web.test_client().post('/api/v1/messages', json={
        'sender': 'a', 'recipient': 'b', 'body': 'simulated text',
    })
    assert simulated.json['status'] == 'simulated'
    assert len(web.test_client().get('/api/v1/messages').json['messages']) == 2


def test_binary_payload_not_persisted_or_logged(tmp_path, capsys):
    from app.blueprints.ims import handle_event
    from app.extensions import db
    app = create_app({'SQLALCHEMY_DATABASE_URI': 'sqlite://'})
    with app.app_context():
        db.create_all()
        handle_event({'type': 'incoming_message', 'sender': 'a', 'recipient': 'b',
                      'content_type': 'application/vnd.3gpp.sms', 'body': 'binary-payload'}, include_body=True)
    output = capsys.readouterr().out
    assert 'unsupported_content_type' in output
    assert 'binary-payload' not in output
    assert app.test_client().get('/api/v1/messages').json['messages'] == []


def test_persistence_failure_rolls_back_and_next_message_succeeds(monkeypatch, capsys):
    from sqlalchemy.exc import SQLAlchemyError
    from app.blueprints.ims import handle_event
    from app.extensions import db
    app = create_app({'SQLALCHEMY_DATABASE_URI': 'sqlite://'})
    event = {'type': 'incoming_message', 'sender': 'a', 'recipient': 'b',
             'content_type': 'text/plain', 'body': 'sensitive text'}
    with app.app_context():
        db.create_all()
        commit = db.session.commit
        with monkeypatch.context() as patch:
            patch.setattr(db.session, 'commit', Mock(side_effect=SQLAlchemyError('sensitive text')))
            handle_event(event)
        handle_event(event)
    output = capsys.readouterr().out
    assert 'persistence_failed' in output
    assert 'sensitive text' not in output
    messages = app.test_client().get('/api/v1/messages').json['messages']
    assert len(messages) == 1
    assert messages[0]['body'] == 'sensitive text'
