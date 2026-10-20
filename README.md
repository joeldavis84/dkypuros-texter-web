# 5G Network Automation

A Flask application for exploring 5G network automation, with IMS text messaging as the initial workflow. The repository root is the application source root. Flask serves an Angular 21 frontend styled with Tailwind CSS 4, and Flask-SQLAlchemy uses SQLAlchemy 2 to persist message requests.

**Outgoing messaging remains simulated:** web/API submissions are stored with `status: simulated`. The PJSUA2 listener saves incoming `text/plain` SIP messages with `status: received` in the same database. Click Refresh in the web interface to see them. Outgoing IMS transmission and binary SMS decoding are not implemented.

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

## Container build and run

Run from the application (repository) root; the final `.` supplies the build context:

```sh
podman build -f kubernetes/Containerfile -t dkypuros-texter:latest .
podman volume create texter-data
podman run --rm -v texter-data:/app/instance dkypuros-texter:latest python3.11 -m flask --app app db init
podman run --rm -p 8080:8080 -v texter-data:/app/instance dkypuros-texter:latest
```

The image builds the Angular frontend and PJSUA2 bindings, installs Python 3.11 dependencies, and runs Gunicorn with the `wsgi:app` entry point on port 8080. Open http://127.0.0.1:8080. The named volume preserves the default SQLite database across container runs. The default startup command initializes missing database tables and supervises Gunicorn plus one IMS listener when a SIP account or IMS interface is configured. Both use the same database. Without SIP configuration, it runs only Gunicorn. The existing deployment environment enables the listener automatically; no additional variables are required.

The init container continues to override the image command with `/app/bin/generate-config.py`, which writes the UE configuration to `/generated/nr-ue.conf` on the shared volume. It does not start the web server or SIP listener.

## REST API

All API routes use `/api/v1` and return JSON, including HTTP errors (`{"error":{"code":400,"message":"..."}}`).

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Process liveness and simulation mode (not database/IMS readiness) |
| POST | `/messages` | Save one simulated request; returns 201 and a `Location` header |
| GET | `/messages?limit=20&offset=0` | Received and simulated messages, newest first; limit 1–100, offset ≥ 0 |
| GET | `/messages/<id>` | Retrieve one message; 404 if absent |

Create a request with curl:

```sh
curl --fail-with-body http://127.0.0.1:5000/api/v1/messages \
  -H 'Content-Type: application/json' \
  -d '{"sender":"sip:alice@example.test","recipient":"sip:bob@example.test","body":"Hello from the 5G automation lab"}'

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

For simulated POST requests, sender and recipient must be nonblank strings of at most 128 characters; body must be nonblank text of at most 1,600 characters. These are demo storage limits, not IMS encoding or segmentation rules. Requests are limited to 16 KiB. Non-JSON content returns 415; malformed JSON or invalid fields return 400. Each POST creates a new record; retries are not idempotent.

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
  services/messaging.py   Simulated and received message persistence
frontend/                 Angular application and Tailwind build configuration
tests/                    Backend API and application tests
wsgi.py                   WSGI entry point
requirements.txt          Runtime Python dependencies
requirements-dev.txt      Test dependencies
```

All HTTP routes, asset serving, and application CLI functionality belong to blueprints; the factory only configures and assembles the app.

For real IMS integration, extend `app/services/messaging.py` with a worker queue connected to the PJSUA2 transport and configured IMS credentials. Add delivery status tracking, timeouts, idempotency, and a background job queue before introducing configurable rate, concurrency, or duration for load runs. Do not run long load-generation loops inside Flask request handlers. Add schema migrations when the model evolves.

## Tests

```sh
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
cd frontend
npm run build
```

Tests use isolated databases and mocked PJSUA2 bindings to cover API behavior, SIP callbacks, received-message persistence across listener/web app instances, environment mapping, interface readiness, error recovery, and process supervision. Live IMS interoperability still needs verification against your deployment.

Framework references: [Flask factories](https://flask.palletsprojects.com/en/stable/patterns/appfactories/), [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/en/stable/quickstart/), [Angular compatibility](https://angular.dev/reference/versions), and [Tailwind with Angular](https://tailwindcss.com/docs/installation/framework-guides/angular).

## PJSUA2 receive integration

The container reads `sipIdentity`, `sipDomain`, `sipServer`, `sipPort`, and `imsInterface` from the deployment. It waits for the IMS interface IPv4 address, binds and advertises that address on UDP/5062, and starts registration through the configured SIP proxy. `sipPort` is the remote server port. Explicit `IMS_*` settings still take precedence.

Incoming text SIP messages are committed to the same `Message` table used by the REST API, with `status: received`; the UI displays that status after Refresh. Registration and receive results are logged as JSON, with message bodies hidden by default. Unsupported binary content is logged without its body and is not saved as text. Database failures produce `persistence_failed` events; they are not retried or reported as successful saves.

For manual use, `flask --app app ims check` validates settings and binding imports; `flask --app app ims listen` starts one listener and creates missing tables. Starting Flask or Gunicorn directly does not start a listener. Do not run a second listener when the container's default startup command is already running one.

See [PJSUA2 setup and validation](docs/pjsua2.md) for the live IMS smoke test and current limitations.
