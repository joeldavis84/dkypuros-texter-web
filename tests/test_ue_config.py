import pytest

from app import create_app
from app.ue_config import load_ue_info


CONFIG = '''
// imsi = "999"; this comment is not a setting
uicc0 = {
  imsi = "001010100000002";
  key = "secret-key";
  opc = "secret-opc";
  pdu_sessions = (
    { id = 1; dnn = "oai"; type = "IPv4"; nssai_sd = 0xffffff; },
    /* Another session */
    { id = 2; dnn = "ims"; type = "IPv4"; nssai_sst = 1; }
  );
}
'''


def test_startup_snapshot_exposes_only_metadata(tmp_path):
    path = tmp_path / 'ue.conf'
    path.write_text(CONFIG)
    app = create_app({'TESTING': True, 'UE_CONFIG_PATH': path})
    # The file is read at startup, not on every browser request.
    path.unlink()
    response = app.test_client().get('/api/v1/ue-info')
    assert response.status_code == 200
    assert response.json == {
        'available': True, 'imsi': '001010100000002',
        'pdu_sessions': [{'id': 1, 'dnn': 'oai'}, {'id': 2, 'dnn': 'ims'}],
    }
    assert 'secret' not in response.text
    assert 'key' not in response.json and 'opc' not in response.json


@pytest.mark.parametrize('contents', [None, '', 'secret malformed configuration',
    CONFIG.replace('"001010100000002"', '001010100000002'),
    CONFIG.replace('id = 2', 'id = "two"'),
    CONFIG.replace('dnn = "ims";', ''), CONFIG[:-3]])
def test_missing_or_invalid_file_is_nonfatal(tmp_path, contents):
    path = tmp_path / 'ue.conf'
    if contents is not None:
        path.write_text(contents)
    app = create_app({'TESTING': True, 'UE_CONFIG_PATH': path})
    client = app.test_client()
    assert client.get('/api/v1/ue-info').json == {
        'available': False, 'imsi': None, 'pdu_sessions': [],
    }
    assert client.get('/api/v1/health').status_code == 200


def test_comment_markers_inside_strings_and_empty_sessions(tmp_path):
    path = tmp_path / 'ue.conf'
    path.write_text(CONFIG.replace('secret-key', '// not a comment /* */ #'))
    assert load_ue_info(path)['available']
    path.write_text('uicc0: { imsi = "00101"; pdu_sessions = (); };')
    assert load_ue_info(path) == {'available': True, 'imsi': '00101', 'pdu_sessions': []}
