"""The model hosts (APPLAUT_MODEL_HOSTS) and the models they must serve (models.lock).

Every host is identical: each role has its own port, and each port serves the
model models.lock pins for that role. A host is used only while both ports
report exactly the pinned model, so a job scored on one host means the same
as one scored on another.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

import httpx

from app.applaut.ai.provider import LlamaServerProvider
from app.config import settings

LOCK = Path(__file__).with_name("models.lock")
ROLE_PORT = {"scorer": 8080, "writer": 8081}
KIND_ROLE = {"score_job": "scorer", "write_docs": "writer", "draft_bullets": "writer"}


@dataclass(frozen=True)
class PinnedModel:
    role: str
    alias: str
    sha256: str
    file: str

    @property
    def served_id(self) -> str:
        """The id the host's server reports (update.sh passes it as --alias)."""
        return f"{self.role}:{self.alias}@{self.sha256[:8]}"


@cache
def pinned_models() -> dict[str, PinnedModel]:
    models = {}
    for line in LOCK.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            role, alias, sha, file, _url = line.split()
            models[role] = PinnedModel(role, alias, sha, file)
    missing = set(ROLE_PORT) - set(models)
    if missing:
        raise RuntimeError(f"models.lock has no line for {sorted(missing)}")
    return models


def host_addresses() -> list[str]:
    return [a.strip() for a in settings.applaut_model_hosts.split(",") if a.strip()]


@dataclass(frozen=True)
class ModelHost:
    address: str

    def url(self, role: str) -> str:
        return f"http://{self.address}:{ROLE_PORT[role]}/v1"

    def provider(self, kind: str) -> LlamaServerProvider:
        role = KIND_ROLE[kind]
        return _provider(self.url(role), pinned_models()[role].served_id)

    async def check(self) -> str | None:
        """None when both ports serve the pinned models; otherwise what is wrong."""
        headers = {"Authorization": f"Bearer {settings.applaut_llm_api_key}"}
        async with httpx.AsyncClient(timeout=10) as client:
            for role, model in pinned_models().items():
                try:
                    r = await client.get(f"{self.url(role)}/models", headers=headers)
                    r.raise_for_status()
                    served = [m.get("id") for m in r.json().get("data", [])]
                except (httpx.HTTPError, ValueError) as exc:
                    return f"{role} at {self.url(role)}: {type(exc).__name__}: {exc}"
                if model.served_id not in served:
                    return f"{role} at {self.url(role)} serves {served}, models.lock pins {model.served_id}"
        return None


@cache
def _provider(url: str, served_id: str) -> LlamaServerProvider:
    return LlamaServerProvider(url, settings.applaut_llm_api_key, served_id, settings.applaut_llm_timeout_seconds)
