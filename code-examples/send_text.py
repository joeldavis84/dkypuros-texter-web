#!/usr/bin/env python3
"""Vibe-coded example: send one text through IMS. Review before adapting."""
from api_client import parser, run, send_text


def main():
    cli = parser('send a simple text and wait for SIP acceptance.')
    cli.add_argument('--message', required=True, help='Text to send (maximum 1600 characters)')
    args = cli.parse_args()
    send_text(args, args.message)


if __name__ == '__main__':
    run(main)
