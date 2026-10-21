from ..extensions import db
from ..models import Message, MessageSipMetadata


def queue_outgoing_message(sender, recipient, body):
    """The dedicated SIP worker claims this record before sending it."""
    message = Message(sender=sender, recipient=recipient, body=body, status="queued")
    db.session.add(message)
    db.session.commit()
    return message


def record_received_message(sender, recipient, body, sip_branch=None):
    """Persist a decoded text SIP MESSAGE in the web application's message store."""
    message = Message(sender=sender, recipient=recipient, body=body, status="received")
    if sip_branch:
        message.sip_metadata = MessageSipMetadata(branch=sip_branch)
    db.session.add(message)
    db.session.commit()
    return message
