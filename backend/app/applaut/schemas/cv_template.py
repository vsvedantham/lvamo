from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel


class CvTemplateResponse(BaseModel):
    """A user's own .docx CV template. `report` (once read): what each job's CV
    fills in (headline, roles with the master-profile entry they show, skills
    rows), `differences` between the upload and the template filled with the
    upload's own text (must be empty to switch it on), `fonts` the server shows
    in another font, `notes` on lines that stay as uploaded."""
    id: UUID
    file_name: str
    status: str  # reading | ready | failed | active | retired | discarded
    ahead: Optional[int] = None  # queue items before it, while reading
    pages: Optional[int] = None
    report: dict = {}
    error: Optional[str] = None
    can_use: bool = False
    created_at: datetime
    finished_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None


class CvTemplateState(BaseModel):
    active: Optional[CvTemplateResponse] = None   # used for every new CV
    latest: Optional[CvTemplateResponse] = None   # an upload not switched on yet (reading, ready or failed)


class TemplatePreviewResponse(BaseModel):
    url: str
    expires_in: int
    file_name: str


PreviewWhich = Literal["original", "rebuilt"]
