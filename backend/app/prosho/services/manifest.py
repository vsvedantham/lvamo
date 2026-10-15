"""prosho.yaml v1 parsing and validation (BETA_PLAN §7).

Every problem comes back as {"line", "path", "message"} so the dashboard can
point the student at the exact line. Nothing here touches the database or
GitHub — see manifest_sync.py for that.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, model_validator

from app.prosho.models.enums import ClaimTargetOp, DemoKind, ProjectType
from app.prosho.modules.data_science import DataSection
from app.prosho.modules.frontend import FrontendSection

MANIFEST_PATH = "prosho.yaml"
MAX_BYTES = 64 * 1024
MAX_CLAIMS = 30

TYPE_FROM_MANIFEST = {"data-science": ProjectType.data_science, "frontend": ProjectType.frontend}
SECTION_FOR_TYPE = {"data-science": "data", "frontend": "frontend"}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Target(_Strict):
    op: ClaimTargetOp
    value: float
    value_hi: Optional[float] = None

    @model_validator(mode="after")
    def _hi(self) -> "Target":
        if self.op == ClaimTargetOp.between:
            if self.value_hi is None:
                raise ValueError("`between` needs both value and value_hi")
            if self.value_hi < self.value:
                raise ValueError("value_hi must be greater than or equal to value")
        elif self.value_hi is not None:
            raise ValueError("value_hi is only used with op: between")
        return self


class ClaimIn(_Strict):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,59}$")
    text: str = Field(min_length=1, max_length=300)
    metric: Optional[str] = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_.-]{0,99}$")
    target: Optional[Target] = None

    @model_validator(mode="after")
    def _metric_target(self) -> "ClaimIn":
        if (self.metric is None) != (self.target is None):
            raise ValueError("a claim needs both `metric` and `target`, or neither (then it's self-reported)")
        return self


class DemoIn(_Strict):
    kind: DemoKind
    url: HttpUrl = Field()


class ManifestV1(_Strict):
    version: Literal[1]
    title: str = Field(min_length=1, max_length=200)
    type: Literal["data-science", "frontend"]
    summary: Optional[str] = Field(default=None, max_length=300)
    problem: Optional[str] = Field(default=None, max_length=5000)
    demo: Optional[DemoIn] = None
    claims: list[ClaimIn] = Field(default_factory=list, max_length=MAX_CLAIMS)
    data: Optional[DataSection] = None
    frontend: Optional[FrontendSection] = None


@dataclass
class ParseResult:
    manifest: Optional[ManifestV1] = None
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.manifest is not None and not self.errors


def _path_str(loc: tuple) -> str:
    out = ""
    for part in loc:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out


def _line_for(root: yaml.Node | None, loc: tuple) -> int | None:
    """Walk the YAML node tree along a pydantic error location; return the
    1-based line of the deepest node that exists (the key itself for an
    unknown or misspelt key)."""
    node, line = root, (root.start_mark.line + 1 if root is not None else None)
    for part in loc:
        if isinstance(node, yaml.MappingNode) and isinstance(part, str):
            match = next(((k, v) for k, v in node.value if isinstance(k, yaml.ScalarNode) and k.value == part), None)
            if match is None:
                break
            line = match[0].start_mark.line + 1
            node = match[1]
        elif isinstance(node, yaml.SequenceNode) and isinstance(part, int) and part < len(node.value):
            node = node.value[part]
            line = node.start_mark.line + 1
        else:
            break
    return line


def _duplicate_keys(node: yaml.Node, path: tuple = ()) -> list[dict[str, Any]]:
    """PyYAML silently keeps the last of two identical keys; a student would
    never notice their first `claims:` vanished. Flag it instead."""
    errors: list[dict[str, Any]] = []
    if isinstance(node, yaml.MappingNode):
        seen: set[str] = set()
        for k, v in node.value:
            key = k.value if isinstance(k, yaml.ScalarNode) else None
            if key is not None and key in seen:
                errors.append({"line": k.start_mark.line + 1, "path": _path_str(path + (key,)),
                               "message": f"`{key}` appears more than once"})
            seen.add(key)
            errors += _duplicate_keys(v, path + ((key,) if key is not None else ()))
    elif isinstance(node, yaml.SequenceNode):
        for i, item in enumerate(node.value):
            errors += _duplicate_keys(item, path + (i,))
    return errors


def _clean_msg(msg: str) -> str:
    msg = re.sub(r"^Value error, ", "", msg)
    return {"Extra inputs are not permitted": "unknown field — check the spelling"}.get(msg, msg)


def parse_manifest(raw: bytes) -> ParseResult:
    if len(raw) > MAX_BYTES:
        return ParseResult(errors=[{"line": None, "path": "", "message": f"prosho.yaml is larger than {MAX_BYTES // 1024} KB"}])
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return ParseResult(errors=[{"line": None, "path": "", "message": "prosho.yaml must be UTF-8 text"}])

    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
        data = yaml.safe_load(text)
    except yaml.MarkedYAMLError as e:
        mark = e.problem_mark or e.context_mark
        return ParseResult(errors=[{"line": mark.line + 1 if mark else None, "path": "",
                                    "message": f"YAML syntax error: {e.problem or e.context}"}])
    except yaml.YAMLError:
        return ParseResult(errors=[{"line": None, "path": "", "message": "YAML syntax error"}])

    if not isinstance(data, dict):
        return ParseResult(errors=[{"line": 1, "path": "", "message": "prosho.yaml must be a mapping of fields (title:, type:, …)"}])

    errors = _duplicate_keys(root)
    try:
        manifest = ManifestV1.model_validate(data)
    except ValidationError as e:
        for err in e.errors():
            errors.append({"line": _line_for(root, err["loc"]), "path": _path_str(err["loc"]),
                           "message": _clean_msg(err["msg"])})
        return ParseResult(errors=_sorted(errors))

    seen: dict[str, int] = {}
    for i, claim in enumerate(manifest.claims):
        if claim.id in seen:
            errors.append({"line": _line_for(root, ("claims", i, "id")), "path": f"claims[{i}].id",
                           "message": f"claim id `{claim.id}` is already used by claims[{seen[claim.id]}]"})
        seen.setdefault(claim.id, i)

    wanted = SECTION_FOR_TYPE[manifest.type]
    for section in SECTION_FOR_TYPE.values():
        if section != wanted and getattr(manifest, section) is not None:
            errors.append({"line": _line_for(root, (section,)), "path": section,
                           "message": f"`{section}:` is for type {next(t for t, s in SECTION_FOR_TYPE.items() if s == section)} "
                                      f"projects — this one is type {manifest.type}"})

    return ParseResult(manifest=None if errors else manifest, errors=_sorted(errors))


def _sorted(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(errors, key=lambda e: (e["line"] is None, e["line"] or 0))
