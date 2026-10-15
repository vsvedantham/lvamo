from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class DataSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    url: HttpUrl
    licence: str | None = Field(default=None, max_length=100)


class DataSection(BaseModel):
    """`data:` in prosho.yaml for data-science projects. Source health checks
    against these URLs arrive in Phase 2."""

    model_config = ConfigDict(extra="forbid")

    sources: list[DataSource] = Field(default_factory=list, max_length=30)
