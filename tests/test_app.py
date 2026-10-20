import pytest

from app import create_app
from app.extensions import db


@pytest.fixture()
def app(tmp_path):
    application = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://", "FRONTEND_DIST": tmp_path, "IMS_ACCOUNT_URI": "sip:alice@example.test"})
    with application.app_context():
        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


def test_message_round_trip(app):
    client = app.test_client()
    payload = {"sender": "sip:alice@example.test", "recipient": "sip:bob@example.test", "body": "Hello"}
    response = client.post('/api/v1/messages', json=payload)
    assert response.status_code == 202
    assert response.json['status'] == 'queued'
    assert client.get(response.headers['Location']).json == response.json
    assert client.get('/api/v1/messages').json['messages'] == [response.json]
    assert client.get('/api/v1/messages?offset=1').json['messages'] == []


@pytest.mark.parametrize('payload', [None, [], {}, {"sender": 42}, {"sender": "a", "recipient": "b", "body": " "}, {"sender": "a", "recipient": "b", "body": "x" * 1601}])
def test_bad_payload(app, payload):
    import json
    response = app.test_client().post('/api/v1/messages', data=json.dumps(payload), content_type='application/json')
    assert response.status_code == 400
    assert 'error' in response.json


def test_errors_and_limits(app):
    client = app.test_client()
    for path in ['/api/v1/messages?limit=101', '/api/v1/messages?offset=-1', '/api/v1/messages?limit=no']:
        assert client.get(path).status_code == 400
    for path in ['/api/v1/messages/999', '/api/v1/missing']:
        response = client.get(path)
        assert response.status_code == 404
        assert response.is_json
    assert client.post('/api/v1/messages', data='bad').status_code == 415
    assert client.post('/api/v1/messages', data='{', content_type='application/json').status_code == 400
    assert client.post('/api/v1/messages', json={"body": "x" * 17000}).status_code == 413


def test_blueprints_cli_and_frontend(app):
    assert all('.' in rule.endpoint for rule in app.url_map.iter_rules())
    assert app.test_cli_runner().invoke(args=['db', 'init']).exit_code == 0
    client = app.test_client()
    assert client.get('/api/v1/health').json['mode'] == 'sip'
    assert client.get('/').status_code == 503
    (app.config['FRONTEND_DIST'] / 'index.html').write_text('<app-root></app-root>')
    assert client.get('/').status_code == 200
    assert client.get('/missing.js').status_code == 404
    assert client.get('/../requirements.txt').status_code == 404


def test_account_sender_and_invalid_recipient(app):
    client = app.test_client()
    assert client.get('/api/v1/sip-account').json == {
        'account_uri': 'sip:alice@example.test', 'enabled': True,
    }
    response = client.post('/api/v1/messages', json={'recipient': 'sip:bob@example.test', 'body': 'hello'})
    assert response.json['sender'] == 'sip:alice@example.test'
    for recipient in ('bob', 'sip:', 'sip:bob@bad host', 'sip:bob@test\r\nX-Evil: yes'):
        assert client.post('/api/v1/messages', json={'recipient': recipient, 'body': 'hello'}).status_code == 400
    assert client.post('/api/v1/messages', json={
        'sender': 'sip:someone-else@test', 'recipient': 'sip:bob@test', 'body': 'hello',
    }).status_code == 400


def test_unconfigured_account_does_not_queue(app):
    app.config['IMS_ACCOUNT_URI'] = ''
    client = app.test_client()
    assert client.get('/api/v1/sip-account').json['enabled'] is False
    assert client.post('/api/v1/messages', json={'recipient': 'sip:bob@test', 'body': 'hello'}).status_code == 503
    assert client.get('/api/v1/messages').json['messages'] == []
