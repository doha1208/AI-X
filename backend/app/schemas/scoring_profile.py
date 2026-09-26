from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.services.scoring_profile import ScoringProfile, validate_profile


class ScoringProfileDraftIn(BaseModel):
    version: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    weights: dict[str, dict[str, float]]
    unknown_score: float

    @model_validator(mode="after")
    def validate_weights(self) -> "ScoringProfileDraftIn":
        validate_profile(
            ScoringProfile(
                version=self.version,
                weights=self.weights,
                unknown_score=self.unknown_score,
            )
        )
        return self


class ScoringProfileOut(BaseModel):
    id: int
    version: str
    name: str
    description: str | None
    weights: dict[str, dict[str, float]]
    unknown_score: float
    status: str
    created_at: datetime
    created_by: str


class ScoreBuildOut(BaseModel):
    id: int
    profile_id: int
    profile_version: str
    status: Literal["queued", "building", "succeeded", "failed"]
    artifact_version: str | None
    error_code: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
