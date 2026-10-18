"""Onboarding chooses the job engine, and the routine setup kit download."""
import importlib.util
import io
import sys
import zipfile

import yaml
from sqlalchemy import select

from app.applaut.models.engine_task import EngineTask
from app.applaut.models.profile import Profile
from app.applaut.models.user import User
from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from tests.applaut.conftest import TEST_EMAIL_DOMAIN

API = "/api/v1/applaut"
PROFILE = {
    "display_name": "Data Engineer", "total_experience_years": 4, "target_roles": ["Data Engineer", "SQL Developer"],
    "target_countries": ["DE"], "employment_types": ["full_time"], "skills": ["Python", "SQL", "PySpark"],
    "languages": ["English"], "good_threshold": 80,
}


async def _new_user(name="Asha Rao"):
    async with AsyncSessionLocal() as db:
        user = User(email=f"onboard{len(name)}{id(name)}{TEST_EMAIL_DOMAIN}", name=name)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user, {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def _profile(user_id) -> Profile:
    async with AsyncSessionLocal() as db:
        return await db.scalar(select(Profile).where(Profile.user_id == user_id))


async def _tasks(profile_id) -> list[str]:
    async with AsyncSessionLocal() as db:
        return [t.kind for t in await db.scalars(select(EngineTask).where(
            EngineTask.profile_id == profile_id, EngineTask.status == "pending"))]


async def test_basic_with_auto_discovery(client):
    user, headers = await _new_user()
    r = await client.post(f"{API}/profiles", json={**PROFILE, "job_engine": "basic", "discovery_enabled": True,
                                                  "discovery_frequency_hours": 12}, headers=headers)
    assert r.status_code == 201, r.text
    p = await _profile(user.id)
    assert (p.job_engine, p.discovery_enabled, p.discovery_frequency_hours, p.good_threshold) == ("basic", True, 12, 80)
    assert await _tasks(p.id) == ["basic_discovery"]


async def test_basic_manual_only(client):
    user, headers = await _new_user()
    r = await client.post(f"{API}/profiles", json={**PROFILE, "job_engine": "basic", "discovery_enabled": False}, headers=headers)
    assert r.status_code == 201
    p = await _profile(user.id)
    assert (p.job_engine, p.discovery_enabled) == ("basic", False)
    assert await _tasks(p.id) == []


async def test_own_routine_never_auto_discovers(client):
    user, headers = await _new_user()
    r = await client.post(f"{API}/profiles", json={**PROFILE, "job_engine": "own_routine", "discovery_enabled": True}, headers=headers)
    assert r.status_code == 201
    p = await _profile(user.id)
    assert (p.job_engine, p.discovery_enabled) == ("own_routine", False)
    assert await _tasks(p.id) == []


async def test_applaut_ai_not_selectable(client):
    _, headers = await _new_user()
    r = await client.post(f"{API}/profiles", json={**PROFILE, "job_engine": "applaut_ai"}, headers=headers)
    assert r.status_code == 422


async def test_setup_kit(client, tmp_path):
    user, headers = await _new_user("Asha Rao")
    await client.post(f"{API}/profiles", json={**PROFILE, "job_engine": "own_routine"}, headers=headers)
    r = await client.get(f"{API}/job-engine/routine/setup-kit", headers=headers)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert "applaut-routine-kit.zip" in r.headers["content-disposition"]

    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    for required in ("README.md", "CLAUDE.md", "SETUP_PROMPT.md", "ROUTINE_PROMPT.md", ".gitignore", "requirements.txt",
                     "scripts/pipeline.py", "scripts/setup.sh", "templates/cv.html.j2", "templates/cover_letter.html.j2",
                     "templates/fonts/Carlito-Regular.ttf", "profile/master_profile.yaml",
                     "config/search_config.yaml", "sql/applaut_reader.sql"):
        assert f"applaut-routine/{required}" in names, required
    assert not any(n.endswith((".tmpl", ".jpg")) for n in names)

    # Nothing from the original author's own routine.
    for n in names:
        if n.endswith((".md", ".py", ".yaml", ".j2", ".sh", ".sql")):
            text = z.read(n).decode()
            for word in ("Venkat", "Vedantham", "EXL", "GlobalLogic", "Opportunity Card"):
                assert word not in text, (n, word)

    z.extractall(tmp_path)
    root = tmp_path / "applaut-routine"
    profile = yaml.safe_load((root / "profile/master_profile.yaml").read_text())
    assert profile["personal"]["name"] == "Asha Rao" and profile["personal"]["email"] == user.email
    assert profile["skills"] == {"Skills": ["Python", "SQL", "PySpark"]} and profile["years_experience"] == 4
    config = yaml.safe_load((root / "config/search_config.yaml").read_text())
    assert config["role_families"] == ["Data Engineer", "SQL Developer"]
    assert config["skill_terms"] == ["Python", "SQL", "PySpark"]
    assert "Data Engineer (m/w/d)" in config["search_terms_de"]
    assert config["max_searches_per_run"] and config["sources"]

    # The kit's own fact guard accepts the generated profile's sample content.
    spec = importlib.util.spec_from_file_location("kit_pipeline", root / "scripts/pipeline.py")
    pipeline = importlib.util.module_from_spec(spec)
    sys.modules["kit_pipeline"] = pipeline
    spec.loader.exec_module(pipeline)
    assert pipeline.file_stem() == "Asha_Rao"
    p = pipeline.profile()
    cv, cl = pipeline.sample_content(p)
    errors: list[str] = []
    pipeline.build_cv_context(p, cv, errors)
    pipeline.build_cl_context(p, cl, "", errors)
    assert errors == []


async def test_setup_kit_needs_login(client):
    assert (await client.get(f"{API}/job-engine/routine/setup-kit")).status_code in (401, 403)
