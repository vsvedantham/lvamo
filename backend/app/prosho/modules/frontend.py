from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class FrontendSection(BaseModel):
    """`frontend:` in prosho.yaml for website/frontend projects. Screenshots
    and Lighthouse panels arrive in Phase 4; the shape is fixed now so
    manifests written today stay valid."""

    model_config = ConfigDict(extra="forbid")

    urls_to_screenshot: list[HttpUrl] = Field(default_factory=list, max_length=10)
    # e.g. {performance: 90, accessibility: 95} — Lighthouse category → minimum score
    lighthouse_targets: dict[str, float] = Field(default_factory=dict, max_length=10)
