from flask import Blueprint, current_app, jsonify, request, url_for
from sqlalchemy import select
from werkzeug.exceptions import HTTPException

from ..extensions import db
from ..models import Message
from ..services.messaging import queue_outgoing_message
from ..ims.config import SipSettings, sip_uri

api = Blueprint("api", __name__, url_prefix="/api/v1")


@api.app_errorhandler(HTTPException)
def http_error(error):
    return jsonify(error={"code": error.code, "message": error.description}), error.code


@api.get("/health")
def health():
    return jsonify(status="ok", service="5g-ims-automation", mode="sip")


@api.get("/sip-account")
def sip_account():
    try:
        settings = SipSettings.from_config(current_app.config)
    except ValueError:
        return jsonify(account_uri='', enabled=False)
    return jsonify(account_uri=settings.account_uri, enabled=True)


@api.get("/messages")
def list_messages():
    try:
        limit = int(request.args.get("limit", "20"))
        offset = int(request.args.get("offset", "0"))
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError
    except ValueError:
        return jsonify(error={"code": 400, "message": "limit must be 1–100 and offset nonnegative."}), 400
    messages = db.session.scalars(select(Message).order_by(Message.id.desc()).limit(limit).offset(offset))
    return jsonify(messages=[message.to_dict() for message in messages], limit=limit, offset=offset)


@api.get("/messages/<int:message_id>")
def get_message(message_id):
    return jsonify(db.get_or_404(Message, message_id).to_dict())


@api.post("/messages")
def create_message():
    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify(error={"code": 400, "message": "Expected a JSON object."}), 400
    values = {}
    for field, maximum in (("recipient", 128), ("body", 1600)):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            return jsonify(error={"code": 400, "message": f"{field} must be nonblank text of at most {maximum} characters."}), 400
        values[field] = value.strip() if field != "body" else value
    try:
        sip_uri(values['recipient'])
    except ValueError as error:
        return jsonify(error={"code": 400, "message": str(error)}), 400
    try:
        settings = SipSettings.from_config(current_app.config)
    except ValueError:
        return jsonify(error={"code": 503, "message": "SIP account is not configured."}), 503
    if 'sender' in data and data['sender'] != settings.account_uri:
        return jsonify(error={"code": 400, "message": "Sender must match this instance's SIP account."}), 400
    message = queue_outgoing_message(sender=settings.account_uri, **values)
    return jsonify(message.to_dict()), 202, {"Location": url_for("api.get_message", message_id=message.id)}
