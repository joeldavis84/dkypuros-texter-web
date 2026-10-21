from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db


class Message(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    sender: Mapped[str] = mapped_column(String(128))
    recipient: Mapped[str] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    sip_metadata: Mapped["MessageSipMetadata | None"] = relationship(
        lazy="joined", cascade="all, delete-orphan", uselist=False
    )

    def to_dict(self):
        timestamp = self.created_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return {"id": self.id, "sender": self.sender, "recipient": self.recipient,
                "body": self.body, "status": self.status,
                "created_at": timestamp.isoformat(),
                "sip_branch": self.sip_metadata.branch if self.sip_metadata else None}


class MessageSipMetadata(db.Model):
    """Separate table so existing message databases need no column migration."""
    message_id: Mapped[int] = mapped_column(ForeignKey("message.id"), primary_key=True)
    branch: Mapped[str] = mapped_column(Text)
