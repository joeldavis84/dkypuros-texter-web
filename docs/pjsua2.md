# PJSUA2 receive integration

The PJSUA2 listener saves incoming `text/plain` SIP MESSAGE bodies in the existing `Message` table with `status="received"`. Sender, recipient, text, and a UTC receipt timestamp are available through `/api/v1/messages` and the web interface's Refresh button. Simulated web/API submissions retain `status="simulated"`; submitting the form still does not transmit SIP traffic.

## Runtime model

The image defaults to `python3.11 -m app.runtime`. It loads `.env` settings, creates missing database tables, and starts Gunicorn on port 8080. When a SIP account or IMS interface is configured, it also starts exactly one `flask --app app ims listen` process. A process exit stops its sibling and fails the container; SIGTERM/SIGINT shuts down both, with a ten-second grace period before forced termination. The configuration-generator init container overrides the image command and runs independently.

The listener owns PJSUA2 on its main thread, with native worker threads disabled. Gunicorn workers never initialize PJSUA2. Each incoming text message is committed before a success event is logged, and its database session is removed after processing. Both processes inherit the same `DATABASE_URL`, defaulting to `instance/texter.db` inside `/app`. The Kubernetes example does not mount a persistent database volume: records can be lost on container replacement. Use a volume at `/app/instance` or an external database if records need to survive replacement.

No schema change is required; table creation only creates missing tables and does not migrate existing schemas.

## Existing deployment environment

| Variable | Listener use |
| --- | --- |
| `sipIdentity=user1` | Account user |
| `sipDomain=dkypuros` | Account domain and registrar (`sip:dkypuros`) |
| `sipServer=192.168.27.57` | Outbound proxy host |
| `sipPort=5060` | Remote proxy port (`sip:192.168.27.57:5060;lr`) |
| `imsInterface=oaitun_ue1p2` | Interface whose IPv4 address is used for binding and advertisement |

The derived account is `sip:user1@dkypuros`. The local listening port defaults to UDP/5062. The listener waits up to 180 seconds for the interface address before initializing PJSUA2 and registering. This waits for an address, not proof of IMS reachability; the UE must establish the PDU session and routes. If the address changes after startup, restart the listener/container to bind the new address.

Explicit `IMS_ACCOUNT_URI`, `IMS_REGISTRAR_URI`, `IMS_PROXY_URI`, `IMS_BIND_ADDRESS`, `IMS_PUBLIC_ADDRESS`, `IMS_PORT`, and `IMS_TRANSPORT` override the derived settings. An explicitly empty registrar disables registration for direct SIP tests. Without an interface, the bind address defaults to `0.0.0.0`. `IMS_USERNAME`, `IMS_PASSWORD`, and `IMS_REALM` configure ordinary SIP Digest authentication. IMS AKA and IPsec/security agreement are not implemented.

The interface address is supplied to both PJSUA2 `TransportConfig.boundAddress` and `publicAddress`: binding alone does not set the advertised address. See the [PJSUA2 transport configuration reference](https://docs.pjsip.org/en/2.16/api/generated/pjsip/group/group__PJSUA2__SIP__Types.html). Verify actual Contact/Via headers and the return route in your IMS environment.

## Manual commands and validation

The Containerfile builds the native PJSUA2 bindings for Python 3.11. They are not installed by `requirements.txt` in a local development environment.

```sh
python3.11 -m flask --app app ims check
# Use only when a listener is not already running in this network namespace:
python3.11 -m flask --app app ims listen
# Optional: also include incoming text in stdout logs:
python3.11 -m flask --app app ims listen --include-body
```

`ims check` validates configuration and imports PJSUA2 without opening sockets. Direct Flask/Gunicorn startup does not launch the listener. `ims listen` initializes missing tables and handles termination while waiting for the interface or processing SIP events.

After rebuilding and deploying the image:

1. Watch `kubectl -n duranta logs -f deployment/texter-web -c web` for `waiting_for_interface`, then `listener_started`, and registration events. `listener_started` means the transport opened; successful registration should report `active: true` and a successful SIP status.
2. Send a `text/plain` SIP MESSAGE to the registered account through your IMS service.
3. Confirm an `incoming_message` event with `status: received`, `persisted: true`, and a `message_id`.
4. Click Refresh in the web interface, or GET `/api/v1/messages`, and confirm the text and `received` status. Create a simulated message and verify both appear in the same list.

The existing SIP OPTIONS probes check reachability, not account registration or database health. The supervisor detects listener process exits; registration failures are visible in its JSON events.

## Limits of this first integration

- Only `text/plain` is stored. Content-type parameters such as `charset=utf-8` are accepted. `application/vnd.3gpp.sms` produces an `unsupported_content_type` event and is not persisted or logged as text. RP/TPDU decoding remains future work.
- Message bodies are stored in the database regardless of whether log bodies are enabled. Logs omit bodies by default.
- A database error rolls back the session and emits `persistence_failed`; later messages can still be processed. There is no durable retry queue. SIP acceptance is not a guarantee of database persistence.
- Each callback creates a record; application-level duplicate detection is not implemented.
- `PjsuaTransport.send_text()` remains a primitive for future outbound integration. The web form does not call it.
- Automated tests use mocked PJSUA2 callbacks and real isolated databases. Live registration, routing, authentication, and receipt must be validated with the IMS network.
