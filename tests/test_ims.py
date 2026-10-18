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
