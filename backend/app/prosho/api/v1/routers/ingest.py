"""Evidence ingestion for the student's CI — authenticated by a per-project
ingest token, not a user JWT (BETA_PLAN §9)."""
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.prosho.schemas.evidence import MAX_BODY_BYTES, IngestRequest, IngestResponse
from app.prosho.services import evidence as evidence_service
from app.prosho.services.ingest_tokens import project_for_token

router = APIRouter(prefix="/ingest")


@router.post("/evidence", response_model=IngestResponse)
async def ingest_evidence(request: Request, authorization: str = Header(default=""), db: AsyncSession = Depends(get_db)):
    token = authorization.removeprefix("Bearer ").strip()
    project = await project_for_token(token, db) if token else None
    if project is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing, unknown or revoked ingest token",
                            headers={"WWW-Authenticate": "Bearer"})

    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"Body is larger than {MAX_BODY_BYTES // 1024} KB — send fewer items per request")
    try:
        payload = IngestRequest.model_validate(json.loads(body))
    except ValidationError as e:
        detail = [{"loc": list(err["loc"]), "msg": err["msg"]} for err in e.errors()]
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Body must be JSON")
    return await evidence_service.ingest(project, payload, db)
