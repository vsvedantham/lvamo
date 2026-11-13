import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, computed_field


class DocumentResponse(BaseModel):
    id: uuid.UUID
    opportunity_id: uuid.UUID
    document_type: str
    generation_mode: str
    content: str
    ai_model: Optional[str]
    is_current: bool
    created_at: datetime
    engine: str
    content_type: str
    r2_key: Optional[str] = Field(default=None, exclude=True)
    details: Optional[dict] = Field(default=None, exclude=True)

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def has_file(self) -> bool:
        """A downloadable PDF exists (fetch a link from /documents/{id}/file)."""
        return self.content_type == "application/pdf" and self.r2_key is not None

    @computed_field
    @property
    def has_details(self) -> bool:
        """An Applaut AI CV whose bullets can be switched (/documents/{id}/details)."""
        return bool(self.details)


class CvBullet(BaseModel):
    fact_id: str
    entry: str  # the role or project it is listed under
    original: str
    tailored: Optional[str]  # the reworded text, when one passed the checks
    use: Literal["tailored", "original"]
    note: Optional[str]  # why the fact is shown as written, when the model's wording wasn't used


class CvDetailsResponse(BaseModel):
    document_id: uuid.UUID
    is_current: bool
    bullets: list[CvBullet]


class BulletChoiceRequest(BaseModel):
    version: Literal["tailored", "original"]


class BulletChoiceResponse(BaseModel):
    document: DocumentResponse  # the CV's new current version
    details: CvDetailsResponse


class DocumentFileResponse(BaseModel):
    url: str
    expires_in: int
    file_name: str


class OpportunityDocumentsResponse(BaseModel):
    opportunity_id: uuid.UUID
    tailored_resume: Optional[DocumentResponse] = None
    cover_letter: Optional[DocumentResponse] = None


class GenerateDocumentsResponse(BaseModel):
    tailored_resume: DocumentResponse
    cover_letter: DocumentResponse
    mode: str


class WriteAgainResponse(BaseModel):
    docs_status: str
