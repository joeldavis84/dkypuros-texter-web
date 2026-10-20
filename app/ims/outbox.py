"""Database outbox, consumed only on the SIP worker's owning thread.

One worker per account/database. Never automatically retry a claimed message:
after a crash or response timeout its remote outcome may be unknown.
"""
import time

from sqlalchemy import select, update

from ..extensions import db
from ..models import Message


class Outbox:
    def __init__(self, transport, sender, emit, response_timeout=45):
        self.transport = transport
        self.sender = sender
        self.emit = emit
        self.response_timeout = response_timeout
        self.inflight = {}
        self.next_scan = 0

    def recover(self):
        # An earlier process may have sent these before dying. Do not resend.
        db.session.execute(update(Message).where(
            Message.sender == self.sender, Message.status == 'sending',
        ).values(status='unknown'))
        db.session.commit()
        db.session.remove()

    def set_status(self, message_id, status):
        result = db.session.execute(update(Message).where(
            Message.id == message_id, Message.sender == self.sender,
            Message.status.in_(('sending', 'unknown')),
        ).values(status=status))
        db.session.commit()
        db.session.remove()
        return bool(result.rowcount)

    def handle_status(self, event):
        message_id, code = event.get('message_id'), event['code']
        if message_id is None or code < 200:
            return
        status = 'sent' if 200 <= code < 300 else ('unknown' if code == 408 else 'failed')
        if self.set_status(message_id, status):
            event['status'] = status
        self.inflight.pop(message_id, None)

    def tick(self):
        now = time.monotonic()
        for message_id, started in list(self.inflight.items()):
            if now - started >= self.response_timeout:
                self.set_status(message_id, 'unknown')
                del self.inflight[message_id]
                self.emit({'type': 'send_timeout', 'message_id': message_id, 'status': 'unknown'})
        if now < self.next_scan:
            return
        self.next_scan = now + 0.5
        # Timed-out native requests retain correlation pointers until completion.
        if len(self.transport.pending_messages) >= 64 or not self.transport.ready_to_send():
            return
        try:
            message = db.session.scalar(select(Message).where(
                Message.status == 'queued', Message.sender == self.sender,
            ).order_by(Message.id).limit(1))
            if message is None:
                return
            message_id, recipient, body = message.id, message.recipient, message.body
            claimed = db.session.execute(update(Message).where(
                Message.id == message_id, Message.status == 'queued',
            ).values(status='sending')).rowcount
            db.session.commit()
        finally:
            # Never hold a read transaction while polling native SIP events.
            db.session.remove()
        if not claimed:
            return
        self.inflight[message_id] = now
        try:
            self.transport.send_text(recipient, body, message_id=message_id)
        except Exception:
            self.inflight.pop(message_id, None)
            self.set_status(message_id, 'failed')
            self.emit({'type': 'send_failed', 'message_id': message_id, 'status': 'failed'})
