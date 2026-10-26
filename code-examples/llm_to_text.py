#!/usr/bin/env python3
"""Vibe-coded example: forward a local LLM completion over IMS. Review before adapting."""
from api_client import parser, request_json, run, send_text


def main():
    cli = parser('ask a local LLM for a chat completion, then send its text through IMS.')
    cli.add_argument('--llm-url', default='http://localhost:11434/v1/chat/completions',
                     help='Full URL of a local OpenAI-compatible chat completions endpoint')
    cli.add_argument('--model', required=True, help='Name of a model already installed on the local LLM server')
    cli.add_argument('--prompt', required=True)
    args = cli.parse_args()
    result = request_json(args.llm_url, {
        'model': args.model,
        'stream': False,
        'messages': [
            {'role': 'system', 'content': 'Answer concisely in plain text, within 1600 characters.'},
            {'role': 'user', 'content': args.prompt},
        ],
    }, timeout=120)
    answer = result['choices'][0]['message']['content']
    if not isinstance(answer, str):
        raise RuntimeError('The LLM did not return text content.')
    # Fail on overlong completions rather than silently truncating their meaning.
    send_text(args, answer.strip())


if __name__ == '__main__':
    run(main)
