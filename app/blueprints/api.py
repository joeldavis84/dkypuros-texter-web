from flask import Blueprint, jsonify, request, url_for
from sqlalchemy import select
from werkzeug.exceptions import HTTPException

from ..extensions import db
from ..models import Message
from ..services.messaging import record_simulated_message

api = Blueprint("api", __name__, url_prefix="/api/v1")


@api.app_errorhandler(HTTPException)
def http_error(error):
    return jsonify(error={"code": error.code, "message": error.description}), error.code


@api.get("/health")
def health():
    return jsonify(status="ok", service="5g-ims-automation", mode="simulation")


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
    for field, maximum in (("sender", 128), ("recipient", 128), ("body", 1600)):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            return jsonify(error={"code": 400, "message": f"{field} must be nonblank text of at most {maximum} characters."}), 400
        values[field] = value.strip() if field != "body" else value
    message = record_simulated_message(**values)
    return jsonify(message.to_dict()), 201, {"Location": url_for("api.get_message", message_id=message.id)}
