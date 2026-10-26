"""Vibe-coded example helper, not a production SDK. Review before adapting."""
import argparse
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request_json(url, payload=None, timeout=10):
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    request = Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f'HTTP {error.code}: {error.read().decode("utf-8", errors="replace")}') from error
    except (URLError, TimeoutError, ValueError) as error:
        raise RuntimeError(f'Request failed: {error}') from error


def parser(description):
    result = argparse.ArgumentParser(description='Vibe-coded example: ' + description)
    result.add_argument('--base-url', default=os.getenv('TEXTER_URL', 'http://localhost:8080'),
                        help='Web app origin (or TEXTER_URL); do not include /api/v1')
    result.add_argument('--recipient', required=True, help='SIP identity, with or without sip:')
    result.add_argument('--dry-run', action='store_true', help='Print payload without submitting a message')
    return result


def send_text(args, body):
    recipient = args.recipient.strip()
    if not recipient.startswith('sip:'):
        recipient = 'sip:' + recipient
    if not body.strip() or len(body) > 1600:
        raise RuntimeError('Message must contain 1–1600 characters; shorten it before sending.')
    if len(recipient) > 128 or any(char.isspace() for char in recipient):
        raise RuntimeError('Recipient must be a SIP URI of at most 128 characters without whitespace.')
    payload = {'recipient': recipient, 'body': body}
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    base = args.base_url.rstrip('/') + '/api/v1/messages'
    # Never retry a POST automatically: a lost response can still mean it was queued.
    try:
        message = request_json(base, payload)
    except RuntimeError as error:
        raise RuntimeError(f'{error}\nSubmission not confirmed. Check Recent messages before retrying.') from error
    message_id = message['id']
    print(f'Queued message #{message_id}; checking {base}/{message_id}', flush=True)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            message = request_json(f'{base}/{message_id}')
        except RuntimeError as error:
            raise RuntimeError(f'Message #{message_id}: status check failed; do not resubmit blindly. {error}') from error
        status = message['status']
        if status == 'sent':
            print(f'Message #{message_id}: accepted by SIP (not a delivery/read receipt).')
            return
        if status not in ('queued', 'sending'):
            raise RuntimeError(f'Message #{message_id}: {status}. Check its status before retrying.')
        time.sleep(1)
    raise RuntimeError(f'Message #{message_id}: still pending after 60 seconds. It may send later; do not resubmit blindly.')


def run(main):
    try:
        main()
    except (RuntimeError, OSError, KeyError, IndexError, TypeError) as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nStopped; any already queued message can still send.', file=sys.stderr)
        sys.exit(130)
