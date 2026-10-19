# 5G Network Automation

A Flask application for exploring 5G network automation, with IMS text messaging as the initial workflow. The repository root is the application source root. Flask serves an Angular 21 frontend styled with Tailwind CSS 4, and Flask-SQLAlchemy uses SQLAlchemy 2 to persist message requests.

**This scaffold only simulates messaging:** requests are stored with `status: simulated`. The web and REST workflows do not transmit IMS messages or generate network load yet.

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

The image builds the Angular frontend and PJSUA2 bindings, installs Python 3.11 dependencies, and runs Gunicorn with the `wsgi:app` entry point on port 8080. Open http://127.0.0.1:8080. The named volume preserves the default SQLite database across container runs. The IMS listener still requires a separate explicit command.

The same image also supplies `/app/bin/render-nr-ue-config.py` for the Kubernetes init container. `kubernetes/yaml/deployment.yaml` overrides `command` to run it before the UE starts. It reads the full template from `templatePath` and writes the rendered configuration to `outputPath` (respectively `/template/nr-ue.conf.tmpl` and `/generated/nr-ue.conf` in the deployment).

Provide the `nr-ue-config-template` ConfigMap with an `nr-ue.conf.tmpl` key containing your complete UE configuration. Use `$imsi`, `$imei`, `$key`, `$opc`, `$mcc`, and `$mnc` placeholders (or `${imsi}`-style braces) wherever subscriber values belong, and `$$` for a literal dollar sign. Values come from the identically named, case-sensitive environment variables and retain leading zeros. The renderer requires all six values and both paths, and fails on missing values or invalid/unknown placeholders. All other template content is preserved.

## REST API

All API routes use `/api/v1` and return JSON, including HTTP errors (`{"error":{"code":400,"message":"..."}}`).

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Process liveness and simulation mode (not database/IMS readiness) |
| POST | `/messages` | Save one simulated request; returns 201 and a `Location` header |
| GET | `/messages?limit=20&offset=0` | Newest requests first; limit 1–100, offset ≥ 0 |
| GET | `/messages/<id>` | Retrieve one request; 404 if absent |

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
  services/messaging.py   Simulation service / future IMS adapter boundary
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

Tests use an isolated in-memory database and cover request persistence, validation, pagination, errors, blueprint registration, database CLI, and frontend serving.

Framework references: [Flask factories](https://flask.palletsprojects.com/en/stable/patterns/appfactories/), [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/en/stable/quickstart/), [Angular compatibility](https://angular.dev/reference/versions), and [Tailwind with Angular](https://tailwindcss.com/docs/installation/framework-guides/angular).

## Preliminary PJSUA2 support

An optional PJSUA2 adapter and `flask --app app ims check` / `ims listen` commands provide configuration validation, a dedicated SIP event loop, registration, and receive/status callbacks. A transport interface and text SIP send primitive are available for future worker integration. The REST API remains simulation-only. See [PJSUA2 setup, architecture, and remaining IMS work](docs/pjsua2.md); native bindings are installed separately from `requirements.txt`.

The IMS listener defaults to **UDP/5062 on all IPv4 interfaces (`0.0.0.0`)** in the network namespace shared with the UE softmodem sidecar. Run it explicitly with `flask --app app ims listen`; starting Flask alone does not start the listener. Existing environment overrides take precedence.
