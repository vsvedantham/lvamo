from datetime import datetime
from typing import Literal

from pydantic import BaseModel, model_validator


class MasterProfileResponse(BaseModel):
    data: dict
    yaml: str
    version: int
    source: str
    updated_at: datetime


class MasterProfileSave(BaseModel):
    """Either the routine's master_profile.yaml as text, or the same data as JSON."""
    yaml: str | None = None
    data: dict | None = None

    @model_validator(mode="after")
    def _one(self):
        if (self.yaml is None) == (self.data is None):
            raise ValueError("send either yaml or data")
        return self


PreviewKind = Literal["cv", "cover_letter"]
