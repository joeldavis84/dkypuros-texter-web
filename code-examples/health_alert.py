#!/usr/bin/env python3
"""Vibe-coded example: send HTTP outage/recovery alerts over IMS. Review before adapting."""
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from api_client import parser, run, send_text


def healthy(url):
    try:
        with urlopen(url, timeout=10) as response:
            return 200 <= response.status < 300
    except (HTTPError, URLError, TimeoutError, OSError):
        return False


def main():
    cli = parser('monitor an HTTP endpoint and send outage/recovery notifications.')
    cli.add_argument('--url', required=True, help='HTTP health endpoint to check')
    cli.add_argument('--name', default='Monitored service', help='Short service name used in messages')
    cli.add_argument('--interval', type=int, default=30, help='Seconds between checks (default: 30)')
    cli.add_argument('--checks', type=int, default=0, help='Stop after this many checks; 0 runs until Ctrl-C')
    args = cli.parse_args()
    if args.interval < 1 or args.checks < 0:
        cli.error('--interval must be positive and --checks must be nonnegative')
    previous = None
    count = 0
    while True:
        current = healthy(args.url)
        timestamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
        print(f'{timestamp}: {args.name}: {"UP" if current else "DOWN"}', flush=True)
        # Initial healthy check is quiet; initial outage and subsequent changes alert.
        if (previous is None and not current) or (previous is not None and current != previous):
            state = 'RECOVERED' if current else 'DOWN'
            send_text(args, f'{args.name}: {state} at {timestamp}')
        previous = current
        count += 1
        if args.checks and count >= args.checks:
            return
        time.sleep(args.interval)


if __name__ == '__main__':
    run(main)
