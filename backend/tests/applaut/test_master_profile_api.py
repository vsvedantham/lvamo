"""Master profile API: save from YAML or JSON, validation errors, versioning, preview PDFs, ownership."""
from app.applaut.documents.profile_schema import to_yaml
from tests.applaut.test_documents import PROFILE

API = "/api/v1/applaut/master-profile"


async def test_no_profile_is_404(client, make_user):
    _, _, headers = await make_user()
    assert (await client.get(API, headers=headers)).status_code == 404
    assert (await client.get(f"{API}/preview/cv", headers=headers)).status_code == 404


async def test_save_yaml_then_json_bumps_version(client, make_user):
    _, _, headers = await make_user()
    r = await client.put(API, json={"yaml": to_yaml(PROFILE)}, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"] == 1 and body["source"] == "yaml"
    assert body["data"]["personal"]["name"] == "Alex Example"
    assert "default_headline:" in body["yaml"]

    edited = {**body["data"], "default_headline": "Data Engineer with Spark and Azure"}
    r = await client.put(API, json={"data": edited}, headers=headers)
    assert r.status_code == 200 and r.json()["version"] == 2 and r.json()["source"] == "manual"
    assert (await client.get(API, headers=headers)).json()["data"]["default_headline"] == edited["default_headline"]


async def test_invalid_profile_lists_problems_and_saves_nothing(client, make_user):
    _, _, headers = await make_user()
    bad = {**PROFILE, "experience": []}
    r = await client.put(API, json={"data": bad}, headers=headers)
    assert r.status_code == 422
    assert any(e.startswith("experience") for e in r.json()["errors"])
    r = await client.put(API, json={"yaml": "personal: [unclosed"}, headers=headers)
    assert r.status_code == 422 and r.json()["errors"][0].startswith("Not valid YAML")
    assert (await client.get(API, headers=headers)).status_code == 404


async def test_must_send_exactly_one_of_yaml_or_data(client, make_user):
    _, _, headers = await make_user()
    assert (await client.put(API, json={}, headers=headers)).status_code == 422
    assert (await client.put(API, json={"yaml": "a: 1", "data": {}}, headers=headers)).status_code == 422


async def test_preview_pdfs(client, make_user):
    _, _, headers = await make_user()
    await client.put(API, json={"data": PROFILE}, headers=headers)
    for kind in ("cv", "cover_letter"):
        r = await client.get(f"{API}/preview/{kind}", headers=headers)
        assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
        assert r.content.startswith(b"%PDF")
    assert (await client.get(f"{API}/preview/other", headers=headers)).status_code == 422


async def test_profiles_are_per_user(client, make_user):
    _, _, a = await make_user()
    _, _, b = await make_user()
    await client.put(API, json={"data": PROFILE}, headers=a)
    assert (await client.get(API, headers=b)).status_code == 404
    assert (await client.get(API)).status_code in (401, 403)
