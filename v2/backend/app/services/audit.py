from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditEvent, User

_FORBIDDEN = {"password", "password_hash", "token", "jwt", "secret"}


def record(db: Session, action: str, *, actor: User | None = None, entity_type: str | None = None,
           entity_id: Any = None, detail: dict[str, Any] | None = None, actor_username: str | None = None) -> AuditEvent:
    """Adds an audit row to the caller's transaction (commits with the business change)."""
    clean = {k: v for k, v in (detail or {}).items() if k.lower() not in _FORBIDDEN}
    ev = AuditEvent(
        actor_id=actor.id if actor else None,
        actor_username=(actor.username if actor else actor_username),
        action=action, entity_type=entity_type,
        entity_id=None if entity_id is None else str(entity_id),
        detail=json.dumps(clean, default=str, sort_keys=True),
    )
    db.add(ev)
    return ev
