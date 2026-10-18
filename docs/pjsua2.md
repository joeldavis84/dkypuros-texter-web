# Preliminary PJSUA2 integration

The Flask project now includes an optional PJSUA2 transport and blueprint CLI. This is SIP groundwork, **not working SMS over IMS**. The web form and REST `/api/v1/messages` still only save simulated records. There is no worker queue or REST-to-SIP handoff yet.

## Runtime model

Run exactly one `flask --app app ims listen` process for an account. It owns the native Endpoint, Account, and Buddy objects, registers if a registrar is configured, and polls events on its main thread. Native worker threads are disabled. Flask/Gunicorn workers never initialize PJSUA2, avoiding duplicate registrations and native state inherited across forks. Ctrl-C and SIGTERM stop the listener and release resources.

`app/ims/transport.py` defines the transport boundary. `PjsuaTransport.send_text()` provides a basic `text/plain` SIP MESSAGE primitive for a future worker consumer. Use it only on the worker's owning thread after startup; it waits for no result and completion is asynchronous through message-status events. It is deliberately not exposed as a REST send endpoint. SIP response codes must not be presented as end-to-end SMS delivery receipts.

The listener emits JSON registration, incoming-message, and message-status events on stdout. Message bodies are omitted unless `--include-body` is supplied. Events are not persisted, and stdout is not a durable queue. Incoming binary SMS payloads are not decoded or guaranteed to survive the SWIG string interface. Treat this listener as a text SIP integration probe only.

## Native dependency

PJSUA2 is not a normal pure-Python dependency. Build a selected PJPROJECT release and its official Python SWIG bindings for the same Python interpreter/ABI used by this application. Native build tools, SWIG, Python development headers, and PJPROJECT dependencies are required. Follow the upstream build instructions, including `-fPIC` on Linux and installation into the active virtual environment. This repository does not download or build native libraries automatically, and does not pin an unverified third-party PyPI wrapper.

Verify within the active virtual environment:

```sh
python -c 'import pjsua2'
flask --app app ims check
```

`ims check` validates settings and imports the binding without opening sockets; it does not verify registration or network reachability. Native bindings and live network interoperability have not been tested here.

## Configuration and running

Copy the `IMS_*` variables from `.env.example` into `.env` and replace the example identity. `IMS_ACCOUNT_URI` is required. Optional registrar and proxy values are `sip:` URIs. For a proxy route, use the parameters required by your deployment, commonly `;lr`. `IMS_USERNAME`, `IMS_PASSWORD`, and `IMS_REALM` support ordinary SIP Digest only, not an IMS AKA credential flow. Credentials are omitted from settings repr and built-in native SIP logging is disabled.

Transport defaults to **UDP on `0.0.0.0:5062`**, listening on all IPv4 interfaces in the shared pod network namespace, including the UE data-plane interface. TCP remains configurable; TLS is not implemented. `IMS_BIND_ADDRESS` can instead select a specific local UE interface address once that address exists. `IMS_PORT` is the local listening port; keep 5062 for the expected IMS return path. Existing `.env` files or deployment environment variables override these defaults and must be updated if they still specify TCP/5060 or loopback.

```sh
flask --app app ims listen
# Optional: include sensitive message text in stdout
flask --app app ims listen --include-body
```

The explicit listen command opens sockets and may send REGISTER traffic. Normal Flask startup does neither.

## Connecting through the OAI UE

The deployment topology is one pod containing this application and the Duranta softmodem sidecar, using `docker.io/oaisoftwarealliance/oai-nr-ue:2026.w39`. Both containers share the same network namespace, interfaces, routes, and port space. The application receives IMS traffic directly on UDP/5062 through the UE's PDU-session interface. There is no separate sidecar hostname, TCP control connection, or sidecar SMS API in this design. Only one process in the pod should bind this SIP port.

PJSUA2 sends SIP toward the IMS network/P-CSCF using the shared namespace's routing table. The softmodem/network setup must establish the PDU session and routes for IMS traffic; the application does not create those interfaces or routes. Binding the wildcard address allows listening before the UE interface appears, but does not establish connectivity or registration readiness. Start registration after the UE data path is ready.

The wildcard listening address is not an advertised SIP contact address. Verify that SIP Contact/Via and the IMS return route use the reachable UE PDU-session IP and UDP/5062, especially when the pod also has a cluster interface. Automatic contact selection and live IMS routing have not yet been validated; explicit advertised-address configuration remains future integration work if needed. No deployment manifests or container build files were changed.

Remaining IMS-specific work includes:

- Confirm UE image capabilities, IMS APN/DNN/PDU session and P-CSCF reachability.
- Establish subscriber identities, IMS AKA/authentication, required headers and any IPsec/security agreement.
- Implement and validate 3GPP SMS RP/TPDU encoding and decoding carried as `application/vnd.3gpp.sms`; `text/plain` is not a substitute.
- Add a durable outbox/worker queue and inbound persistence, correlation IDs, timeouts, idempotency, retries and delivery-report processing.
- Introduce schema migrations before changing the existing message schema.
- Add real-network interoperability tests before exposing load controls.

References: [PJSUA2 Python builds](https://docs.pjsip.org/en/2.15.1/pjsua2/building.html), [threading and object lifetime](https://docs.pjsip.org/en/2.16/pjsua2/general_concept.html), [accounts](https://docs.pjsip.org/en/latest/pjsua2/using/account.html), [instant messaging](https://docs.pjsip.org/en/latest/pjsua2/using/presence.html).
