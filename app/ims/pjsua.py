"""Optional PJSUA2 adapter. text/plain SIP messages are NOT encoded IMS SMS."""
import importlib
import threading

from .config import sip_uri


def load_binding():
    try:
        return importlib.import_module('pjsua2')
    except (ImportError, OSError) as error:
        raise RuntimeError('PJSUA2 native Python binding is unavailable; see docs/pjsua2.md.') from error


class PjsuaTransport:
    def __init__(self, settings, on_event, binding=None):
        self.settings = settings
        self.on_event = on_event
        self.pj = binding
        self.endpoint = None
        self.account = None
        self.buddies = {}
        self.owner = None
        self.pending_messages = {}

    def _check_thread(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError('PJSUA2 must be used on its owning worker thread.')

    def start(self):
        if self.owner is not None:
            raise RuntimeError('Transport already started; create a new instance to restart.')
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError('Start PJSUA2 in a dedicated process main thread.')
        self.pj = self.pj or load_binding()
        self.owner = threading.get_ident()
        pj = self.pj
        emit = self.on_event
        pending = self.pending_messages

        class Account(pj.Account):
            def onRegState(self, prm):
                info = self.getInfo()
                emit({'type': 'registration', 'code': prm.code, 'active': info.regIsActive})

            def onInstantMessage(self, prm):
                emit({'type': 'incoming_message', 'sender': prm.fromUri,
                      'recipient': prm.toUri, 'content_type': prm.contentType,
                      'body': prm.msgBody})

            def onInstantMessageStatus(self, prm):
                # A SIP response is not an SMS delivery receipt.
                token = getattr(prm, 'userData', None)
                entry = pending.get(token)
                response = getattr(prm, 'rdata', None)
                event = {
                    'type': 'message_status', 'recipient': prm.toUri, 'code': prm.code,
                    'reason': getattr(prm, 'reason', ''),
                    # PJSUA2 leaves rdata empty for local timeout/transport errors.
                    # Do not log wholeMsg: it may contain message text or credentials.
                    'response_received': bool(getattr(response, 'wholeMsg', '')),
                    'response_source': getattr(response, 'srcAddress', ''),
                }
                if entry is not None:
                    event['message_id'] = entry[1]
                    if prm.code >= 200:
                        del pending[token]
                emit(event)

        try:
            self.endpoint = pj.Endpoint()
            self.endpoint.libCreate()
            config = pj.EpConfig()
            config.uaConfig.threadCnt = 0
            config.uaConfig.mainThreadOnly = True
            config.logConfig.level = 0
            config.logConfig.consoleLevel = 0
            self.endpoint.libInit(config)
            transport = pj.TransportConfig()
            transport.boundAddress = self.settings.bind_address or '0.0.0.0'
            if self.settings.public_address:
                transport.publicAddress = self.settings.public_address
            transport.port = self.settings.port
            kind = pj.PJSIP_TRANSPORT_TCP if self.settings.transport == 'tcp' else pj.PJSIP_TRANSPORT_UDP
            transport_id = self.endpoint.transportCreate(kind, transport)
            self.endpoint.libStart()
            self.endpoint.audDevManager().setNullDev()
            config = pj.AccountConfig()
            config.natConfig.contactRewriteUse = 0
            config.natConfig.viaRewriteUse = 0
            config.idUri = self.settings.account_uri
            config.regConfig.registrarUri = self.settings.registrar_uri
            config.regConfig.delayBeforeRefreshSec = 25
            config.sipConfig.transportId = transport_id
            if self.settings.proxy_uri:
                config.sipConfig.proxies.append(self.settings.proxy_uri)
            if self.settings.username:
                config.sipConfig.authCreds.append(pj.AuthCredInfo(
                    'digest', self.settings.realm, self.settings.username, 0, self.settings.password))
            self.account = Account()
            self.account.create(config)
        except BaseException:
            self.close()
            raise

    def poll(self, timeout_ms=100):
        self._check_thread()
        if self.endpoint is None:
            raise RuntimeError('Transport is not running.')
        self.endpoint.libHandleEvents(timeout_ms)

    def ready_to_send(self):
        self._check_thread()
        return self.account is not None and (
            not self.settings.registrar_uri or self.account.getInfo().regIsActive
        )

    def send_text(self, recipient, body, message_id=None):
        self._check_thread()
        if self.account is None:
            raise RuntimeError('Transport is not running.')
        sip_uri(recipient)
        if not isinstance(body, str) or not body.strip() or len(body) > 1600:
            raise ValueError('Text must contain 1–1600 characters.')
        if self.settings.registrar_uri and not self.account.getInfo().regIsActive:
            raise RuntimeError('SIP account is not registered.')
        if recipient not in self.buddies:
            if len(self.buddies) >= 100:
                raise RuntimeError('Demo transport supports at most 100 distinct recipients.')
            config = self.pj.BuddyConfig()
            config.uri = recipient
            config.subscribe = False
            buddy = self.pj.Buddy()
            buddy.create(self.account, config)
            self.buddies[recipient] = buddy
        params = self.pj.SendInstantMessageParam()
        params.contentType = 'text/plain'
        params.content = body
        token = None
        if message_id is not None:
            # Python SWIG accepts a wrapped pointer for void* input and returns
            # it as an integer. Keep the parameter alive until the final callback
            # so its address cannot be reused by another outstanding message.
            token = int(params.this)
            params.userData = params.this
            self.pending_messages[token] = (params, message_id)
        try:
            self.buddies[recipient].sendInstantMessage(params)
            self.on_event({
                'type': 'message_submitted', 'message_id': message_id,
                'sender': self.settings.account_uri, 'recipient': recipient,
                'proxy': self.settings.proxy_uri,
                'bind_address': self.settings.bind_address,
                'port': self.settings.port,
            })
        except Exception:
            self.pending_messages.pop(token, None)
            raise

    def close(self):
        if self.owner is None:
            return
        self._check_thread()
        # Release SWIG-owned objects on this thread before destroying the endpoint.
        self.buddies.clear()
        try:
            if self.account is not None:
                try:
                    self.account.shutdown()
                finally:
                    self.account = None
        finally:
            if self.endpoint is not None:
                try:
                    self.endpoint.libDestroy()
                finally:
                    self.endpoint = None
                    self.pending_messages.clear()
