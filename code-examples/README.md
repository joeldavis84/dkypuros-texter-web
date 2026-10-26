# API code examples

These are **vibe-coded examples** for exploring the texter REST API, not a
production SDK or monitoring system. Each script labels itself accordingly.
Read and adapt them for your environment. They use Python 3.11+ and only the
standard library; no additional pip packages are needed.

| Script | Demonstrates |
| --- | --- |
| `send_text.py` | Submit a simple text and poll its SIP send status. |
| `llm_to_text.py` | Request a chat completion from a local LLM and forward its answer as a text. |
| `health_alert.py` | Check an HTTP service and send outage and recovery notifications. |
| `api_client.py` | Shared JSON HTTP requests, validation, and bounded status polling. |

## Setup and API behavior

Run the commands below from the repository root. Set the URL to the web app's
origin, without `/api/v1`. The app needs a configured SIP account and a running
IMS listener with connectivity to your IMS service. Recipients must be routable
through that service.

```sh
export TEXTER_URL='http://localhost:8080'
# For a deployment, use its accessible web app URL instead.
```

Every script also accepts `--base-url` to override `TEXTER_URL`, `--recipient`,
and `--dry-run`. The scripts accept recipients with or without `sip:` and add
that prefix before calling the API. Run a script with `--help` for all options.
They omit `sender`, so the application sends as its configured SIP identity.

The shared client calls `POST /api/v1/messages` with JSON `recipient` and `body`.
HTTP 202 means queued. It prints the returned ID and polls
`GET /api/v1/messages/<id>` once per second, for approximately 60 seconds (an
in-flight HTTP request may take up to another 10 seconds).

- `sent`: accepted by SIP; no recipient delivery or read receipt is required.
- `failed` or `unknown`: exit with an error describing the outcome.
- Still `queued` or `sending` at the deadline: exit with a pending-status error.

A timeout does **not** cancel a queued message. A failed submission response can
also leave a queued message behind. These examples never automatically retry a
POST; check Recent messages or the individual message endpoint before retrying.
The detail endpoint works even for outgoing self-messages hidden from the UI list.
Exit code 0 means success (or dry run), 1 means a request/send error, 2 means
invalid CLI arguments, and 130 means interrupted.

## 1. Send a simple text

```sh
python3 code-examples/send_text.py \
  --recipient user1@dkypuros \
  --message 'Hello from the API'
```

Preview the JSON without contacting the texter app:

```sh
python3 code-examples/send_text.py \
  --recipient user1@dkypuros --message 'Hello from the API' --dry-run
```

Message bodies must be nonblank and at most 1,600 characters; recipient URIs
must be at most 128 characters including `sip:`.

## 2. Send a local LLM chat completion

Start your local LLM server and install a model using that server's own setup
instructions. Supply the exact installed model name. The example defaults to
`http://localhost:11434/v1/chat/completions`, the local
[Ollama-compatible chat endpoint](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx).
You can set `--llm-url` to another local server implementing the same JSON API.
No cloud LLM account or Python LLM SDK is needed.

```sh
python3 code-examples/llm_to_text.py \
  --recipient user1@dkypuros \
  --model YOUR_INSTALLED_MODEL \
  --prompt 'Explain what an IMS PDU session is in two sentences.' \
  --dry-run
```

Remove `--dry-run` to send the answer through IMS. Dry run **still calls the LLM**
but only prints the resulting texter payload. The script sends a system prompt
and your user prompt with `stream: false`, then reads
`choices[0].message.content`. It allows 120 seconds for inference and rejects
empty or overlong answers rather than silently truncating them. This is a
single chat-completion request, not an automatic bot listening for incoming SIP
messages. No conversation history is retained between runs.

## 3. Send service outage and recovery alerts

Use this when you want a SIP notification about a lab service's availability:

```sh
python3 code-examples/health_alert.py \
  --recipient user1@dkypuros \
  --url http://localhost:9000/health \
  --name 'Lab telemetry service' \
  --interval 30
```

The first healthy check is quiet. The first unhealthy check sends a `DOWN`
message, and a later healthy check sends `RECOVERED`. Unchanged states do not
send more messages. HTTP 2xx is healthy; other statuses and connection failures
are unhealthy. Redirects follow Python's normal HTTP behavior. Alerts contain
the service name and UTC timestamp, not the response body.

Add `--checks 3 --dry-run` for a bounded demonstration with no SIP submissions.
Dry run still checks the service. Otherwise use Ctrl-C to stop. Checks run
sequentially, so waiting for an alert's SIP result delays the next check.
State is kept only in memory: restarting during an outage sends a new initial
alert. A send error stops the script rather than retrying an uncertain delivery.
This deliberately simple example does not debounce flapping services, persist
state, or replace a production monitoring system.
