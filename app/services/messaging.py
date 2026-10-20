from ..extensions import db
from ..models import Message


def record_simulated_message(sender, recipient, body):
    """IMS messaging integration belongs here; this scaffold performs no network sends."""
    message = Message(sender=sender, recipient=recipient, body=body, status="simulated")
    db.session.add(message)
    db.session.commit()
    return message


def record_received_message(sender, recipient, body):
    """Persist a decoded text SIP MESSAGE in the web application's message store."""
    message = Message(sender=sender, recipient=recipient, body=body, status="received")
    db.session.add(message)
    db.session.commit()
    return message
