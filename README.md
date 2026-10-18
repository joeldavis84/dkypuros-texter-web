# Duranta IMS Texter

A basic Flask application for an eventual Duranta IMS text messaging demo. The repository root is the application source root. Flask serves an Angular 21 frontend styled with Tailwind CSS 4, and Flask-SQLAlchemy uses SQLAlchemy 2 to persist message requests.

**This scaffold only simulates messaging:** requests are stored with `status: simulated`. It does not connect to Duranta, transmit IMS messages, or generate network load yet.

## Local setup

Requires Python 3.11+ and Node.js 22.12+ (22.x) or 24.x with npm.

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
flask --app app db init
cd frontend
npm install
npm run build
cd ..
flask --app app run --debug
```

Open http://127.0.0.1:5000. Initialize the database before creating or listing messages. `db init` creates missing tables without deleting existing records; it does not migrate changed schemas. The default database is `instance/texter.db`, ignored by Git. Set `DATABASE_URL` to override it; other database engines also require their corresponding Python driver.

For frontend development, run Flask as above and, in a second terminal, run `cd frontend && npm start`. Open http://127.0.0.1:4200; Angular proxies `/api/**` to Flask on port 5000. Rebuild the frontend to update the version served directly by Flask. Before building, Flask's `/` returns an explanatory 503; the API remains available.

To run without the development server after building and initializing the database:

```sh
gunicorn --bind 127.0.0.1:8000 wsgi:app
```

Flask CLI loads `.env` automatically. With Gunicorn, export `DATABASE_URL` in the process environment if overriding the default. This is a local demo with no authentication; add access controls before exposing it beyond a trusted lab.

## REST API

All API routes use `/api/v1` and return JSON, including HTTP errors (`{"error":{"code":400,"message":"..."}}`).

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Process liveness and simulation mode (not database/Duranta readiness) |
| POST | `/messages` | Save one simulated request; returns 201 and a `Location` header |
| GET | `/messages?limit=20&offset=0` | Newest requests first; limit 1–100, offset ≥ 0 |
| GET | `/messages/<id>` | Retrieve one request; 404 if absent |

Create a request with curl:

```sh
curl --fail-with-body http://127.0.0.1:5000/api/v1/messages \
  -H 'Content-Type: application/json' \
  -d '{"sender":"sip:alice@example.test","recipient":"sip:bob@example.test","body":"Hello from Duranta"}'

curl --fail-with-body 'http://127.0.0.1:5000/api/v1/messages?limit=10'
```

Or use Python's standard library (no extra dependency):

```python
import json
from urllib.request import Request, urlopen

request = Request(
    "http://127.0.0.1:5000/api/v1/messages",
    data=json.dumps({
        "sender": "sip:alice@example.test",
        "recipient": "sip:bob@example.test",
        "body": "Hello from Python",
    }).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urlopen(request, timeout=10) as response:
    print(json.load(response))
```

Sender and recipient must be nonblank strings of at most 128 characters; body must be nonblank text of at most 1,600 characters. These are demo storage limits, not IMS encoding or segmentation rules. Requests are limited to 16 KiB. Non-JSON content returns 415; malformed JSON or invalid fields return 400. Each POST creates a new record; retries are not idempotent.

## Structure and extension points

```text
app/
  __init__.py             Application factory and blueprint registration
  extensions.py           Unbound SQLAlchemy extension
  models.py               Message persistence model
  blueprints/
    api.py                Versioned REST API and HTTP error handling
    web.py                Built Angular page and asset serving
    database.py           Database initialization CLI
  services/messaging.py   Simulation service / future Duranta adapter boundary
frontend/                 Angular application and Tailwind build configuration
tests/                    Backend API and application tests
wsgi.py                   WSGI entry point
requirements.txt          Runtime Python dependencies
requirements-dev.txt      Test dependencies
```

All HTTP routes, asset serving, and application CLI functionality belong to blueprints; the factory only configures and assembles the app. No container build files are needed or modified by this scaffold.

For real IMS integration, extend `app/services/messaging.py` with the agreed Duranta REST contract and credentials. Add delivery status tracking, timeouts, idempotency, and a background job queue before introducing configurable rate, concurrency, or duration for load runs. Do not run long load-generation loops inside Flask request handlers. Add schema migrations when the model evolves.

## Tests

```sh
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
cd frontend
npm run build
```

Tests use an isolated in-memory database and cover request persistence, validation, pagination, errors, blueprint registration, database CLI, and frontend serving.

Framework references: [Flask factories](https://flask.palletsprojects.com/en/stable/patterns/appfactories/), [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/en/stable/quickstart/), [Angular compatibility](https://angular.dev/reference/versions), and [Tailwind with Angular](https://tailwindcss.com/docs/installation/framework-guides/angular).

## Preliminary PJSUA2 support

An optional PJSUA2 adapter and `flask --app app ims check` / `ims listen` commands provide configuration validation, a dedicated SIP event loop, registration, and receive/status callbacks. A transport interface and text SIP send primitive are available for future worker integration. The REST API remains simulation-only. See [PJSUA2 setup, architecture, and remaining IMS work](docs/pjsua2.md); native bindings are installed separately from `requirements.txt`.

The IMS listener defaults to **UDP/5062 on all IPv4 interfaces (`0.0.0.0`)** in the network namespace shared with the Duranta softmodem sidecar. Run it explicitly with `flask --app app ims listen`; starting Flask alone does not start the listener. Existing environment overrides take precedence.
