"""Read the UE's libconfig-style file and expose only displayable metadata."""
import json
from pathlib import Path
import re


TOKEN = re.compile(
    r'\s+|//[^\n]*|\#[^\n]*|/\*.*?\*/|'
    r'"(?:\\.|[^"\\])*"|[A-Za-z_][\w-]*|'
    r'-?(?:0[xX][0-9a-fA-F]+|\d+(?:\.\d+)?)|[{}()\[\]=:;,]',
    re.DOTALL,
)


def parse_config(text):
    tokens = []
    position = 0
    for match in TOKEN.finditer(text):
        if match.start() != position:
            raise ValueError('Invalid configuration syntax')
        position = match.end()
        token = match.group()
        if not token.isspace() and not token.startswith(('//', '#', '/*')):
            tokens.append(token)
    if position != len(text):
        raise ValueError('Invalid configuration syntax')
    index = 0

    def take():
        nonlocal index
        if index >= len(tokens):
            raise ValueError('Unexpected end of configuration')
        value = tokens[index]
        index += 1
        return value

    def fields(end=None):
        result = {}
        while index < len(tokens) and tokens[index] != end:
            name = take()
            if not re.fullmatch(r'[A-Za-z_][\w-]*', name) or take() not in ('=', ':'):
                raise ValueError('Invalid assignment')
            if name in result:
                raise ValueError('Duplicate setting')
            result[name] = value()
            if index < len(tokens) and tokens[index] in (';', ','):
                take()
            elif index < len(tokens) and tokens[index] != end:
                raise ValueError('Missing setting separator')
        if end is not None and take() != end:
            raise ValueError('Unclosed group')
        return result

    def value():
        token = take()
        if token == '{':
            return fields('}')
        if token in ('(', '['):
            end = ')' if token == '(' else ']'
            items = []
            while index < len(tokens) and tokens[index] != end:
                items.append(value())
                if index < len(tokens) and tokens[index] == ',':
                    take()
                elif index < len(tokens) and tokens[index] != end:
                    raise ValueError('Missing list separator')
            if take() != end:
                raise ValueError('Unclosed list')
            return items
        if token.startswith('"'):
            return json.loads(token)
        if re.fullmatch(r'-?\d+', token):
            return int(token)
        if re.fullmatch(r'[A-Za-z_][\w-]*|-?(?:0[xX][0-9a-fA-F]+|\d+\.\d+)', token):
            return token
        raise ValueError('Invalid value')

    return fields()


def load_ue_info(path):
    try:
        config = parse_config(Path(path).read_text(encoding='utf-8'))
        uicc = config['uicc0']
        imsi, sessions = uicc['imsi'], uicc['pdu_sessions']
        if not isinstance(imsi, str) or not re.fullmatch(r'[0-9]+', imsi):
            raise ValueError('Invalid IMSI')
        if not isinstance(sessions, list):
            raise ValueError('Invalid PDU sessions')
        display_sessions = []
        for session in sessions:
            session_id, dnn = session['id'], session['dnn']
            if type(session_id) is not int or session_id < 1 or not isinstance(dnn, str) or not dnn:
                raise ValueError('Invalid PDU session')
            display_sessions.append({'id': session_id, 'dnn': dnn})
        return {'available': True, 'imsi': imsi, 'pdu_sessions': display_sessions}
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, RecursionError):
        # Never return parser errors or file contents, which can contain credentials.
        return {'available': False, 'imsi': None, 'pdu_sessions': []}
