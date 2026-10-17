import uuid
from datetime import datetime
from typing import Optional

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

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def has_file(self) -> bool:
        """A downloadable PDF exists (fetch a link from /documents/{id}/file)."""
        return self.content_type == "application/pdf" and self.r2_key is not None


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
