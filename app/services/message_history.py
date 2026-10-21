"""Presentation of message history without changing stored delivery states."""
import re

from sqlalchemy import select

from ..extensions import db
from ..models import Message


def sip_identity(address):
    address = address.strip()
    enclosed = re.search(r'<([^<>]+)>', address)
    if enclosed:
        address = enclosed.group(1).strip()
    if not address.lower().startswith('sip:'):
        return None
    address = address[4:].split('?', 1)[0].split(';', 1)[0]
    user, separator, domain = address.rpartition('@')
    if not separator or not user or not domain:
        return None
    # Preserve the user part's case; host names are case-insensitive.
    return user, domain.lower()


def recent_messages(account_uri, limit, offset):
    identity = sip_identity(account_uri)
    results = []
    visible = 0
    # Apply pagination to visible records, not raw sent/received database rows.
    rows = db.session.scalars(select(Message).order_by(Message.id.desc()).execution_options(yield_per=100))
    try:
        for message in rows:
            is_self = identity is not None and (
                sip_identity(message.sender) == identity == sip_identity(message.recipient)
            )
            if is_self and message.status != 'received':
                continue
            if visible < offset:
                visible += 1
                continue
            item = message.to_dict()
            if is_self:
                item['status'] = 'self'
            results.append(item)
            if len(results) == limit:
                break
    finally:
        rows.close()
    return results
