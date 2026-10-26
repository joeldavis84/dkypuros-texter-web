"""Exercise example workflows without a live IMS or LLM service."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / 'code-examples'


def load(name, monkeypatch):
    spec = importlib.util.spec_from_file_location(name, EXAMPLES / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def client(monkeypatch):
    return load('api_client', monkeypatch)


def test_send_posts_once_and_waits_for_sip(client, monkeypatch):
    request = Mock(side_effect=[{'id': 7}, {'status': 'sending'}, {'status': 'sent'}])
    monkeypatch.setattr(client, 'request_json', request)
    monkeypatch.setattr(client.time, 'sleep', lambda _: None)
    client.send_text(SimpleNamespace(recipient='user1@dkypuros', base_url='http://texter', dry_run=False), 'hello')
    assert request.call_args_list[0].args == ('http://texter/api/v1/messages', {'recipient': 'sip:user1@dkypuros', 'body': 'hello'})
    assert all(call.args == ('http://texter/api/v1/messages/7',) for call in request.call_args_list[1:])


def test_uncertain_submission_not_retried(client, monkeypatch):
    request = Mock(side_effect=RuntimeError('connection lost'))
    monkeypatch.setattr(client, 'request_json', request)
    with pytest.raises(RuntimeError, match='Check Recent messages'):
        client.send_text(SimpleNamespace(recipient='a@test', base_url='http://texter', dry_run=False), 'hello')
    assert request.call_count == 1


def test_dry_run_and_length_limit(client, monkeypatch, capsys):
    request = Mock()
    monkeypatch.setattr(client, 'request_json', request)
    args = SimpleNamespace(recipient='a@test', dry_run=True)
    client.send_text(args, 'hello')
    assert 'sip:a@test' in capsys.readouterr().out
    with pytest.raises(RuntimeError, match='1600'):
        client.send_text(args, 'x' * 1601)
    request.assert_not_called()


def test_llm_completion_forwarded(client, monkeypatch):
    llm = load('llm_to_text', monkeypatch)
    monkeypatch.setattr(sys, 'argv', ['llm_to_text.py', '--recipient', 'a@test', '--model', 'local', '--prompt', 'Hi', '--dry-run'])
    request = Mock(return_value={'choices': [{'message': {'content': 'An answer'}}]})
    send = Mock()
    monkeypatch.setattr(llm, 'request_json', request)
    monkeypatch.setattr(llm, 'send_text', send)
    llm.main()
    assert request.call_args.args[1]['messages'][1]['content'] == 'Hi'
    assert send.call_args.args[1] == 'An answer'
    assert send.call_args.args[0].dry_run


def test_health_alerts_only_on_changes(client, monkeypatch):
    health = load('health_alert', monkeypatch)
    monkeypatch.setattr(sys, 'argv', ['health_alert.py', '--recipient', 'a@test', '--url', 'http://service', '--checks', '5'])
    monkeypatch.setattr(health, 'healthy', Mock(side_effect=[True, False, False, True, True]))
    monkeypatch.setattr(health.time, 'sleep', lambda _: None)
    send = Mock()
    monkeypatch.setattr(health, 'send_text', send)
    health.main()
    assert send.call_count == 2
    assert ': DOWN at ' in send.call_args_list[0].args[1]
    assert ': RECOVERED at ' in send.call_args_list[1].args[1]
