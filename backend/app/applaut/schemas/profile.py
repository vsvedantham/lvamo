import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.applaut.models.enums import EmploymentTypeEnum, RemotePreferenceEnum


class CreateProfileRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    total_experience_years: Optional[int] = Field(default=None, ge=0, le=50)
    target_roles: list[str] = Field(min_length=1)
    target_countries: list[str] = Field(min_length=1)
    remote_preference: RemotePreferenceEnum = RemotePreferenceEnum.any
    employment_types: list[EmploymentTypeEnum] = Field(min_length=1)
    skills: list[str] = []
    languages: list[str] = []
    discovery_frequency_hours: Literal[6, 12, 24] = 24
    good_threshold: int = Field(default=85, ge=70, le=100)


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    total_experience_years: Optional[int] = Field(default=None, ge=0, le=50)
    target_roles: Optional[list[str]] = None
    target_countries: Optional[list[str]] = None
    remote_preference: Optional[RemotePreferenceEnum] = None
    employment_types: Optional[list[EmploymentTypeEnum]] = None
    skills: Optional[list[str]] = None
    languages: Optional[list[str]] = None
    discovery_frequency_hours: Optional[Literal[6, 12, 24]] = None
    good_threshold: Optional[int] = Field(default=None, ge=70, le=100)


class ProfileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    display_name: str
    total_experience_years: Optional[int]
    target_roles: list[str]
    target_countries: list[str]
    remote_preference: str
    employment_types: list[str]
    skills: list[str]
    languages: list[str]
    discovery_frequency_hours: int
    discovery_enabled: bool
    good_threshold: int
    job_engine: str
    near_miss_threshold: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def compute_near_miss(self) -> "ProfileResponse":
        self.near_miss_threshold = self.good_threshold - 15
        return self
