import enum
import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.prosho.models.prosho_audit_log import ProshoAuditLog


def _jsonable(v: Any) -> Any:
    if isinstance(v, enum.Enum):
        return v.value
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    return v


def record(
    db: AsyncSession,
    *,
    actor_id: Optional[uuid.UUID],
    action: str,
    entity: str,
    entity_id: Optional[uuid.UUID],
    before: Optional[dict[str, Any]] = None,
    after: Optional[dict[str, Any]] = None,
) -> None:
    """Adds an audit row to the caller's transaction — it commits (or rolls
    back) together with the change it describes."""
    db.add(ProshoAuditLog(
        actor_id=actor_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        before={k: _jsonable(v) for k, v in before.items()} if before is not None else None,
        after={k: _jsonable(v) for k, v in after.items()} if after is not None else None,
    ))
