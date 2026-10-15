"""prosho.yaml validation — valid, invalid, partial; line numbers."""
from app.prosho.services.manifest import MAX_BYTES, parse_manifest

VALID = b"""\
version: 1
title: HeatRisk EU
type: data-science            # data-science | frontend  (beta)
summary: Who is most at risk from summer heat in five European countries
problem: >
  Each country counts heat deaths differently; no open cross-country view
  links how hot it gets to who is exposed and how many people die.
demo:
  kind: streamlit
  url: https://heatrisk.streamlit.app
claims:
  - id: predict-2026
    text: Predict 2026 heat deaths within 25% of official estimates
    metric: prediction_error_pct
    target: { op: abs_lte, value: 25 }
  - id: city-maps
    text: 1 km heat vulnerability maps for five capitals
data:
  sources:
    - name: Eurostat weekly deaths by NUTS 3
      url: https://ec.europa.eu/eurostat/
      licence: CC BY 4.0
"""


def errs(raw: bytes):
    r = parse_manifest(raw)
    assert not r.ok
    return [(e["line"], e["path"], e["message"]) for e in r.errors]


def test_plan_example_is_valid():
    r = parse_manifest(VALID)
    assert r.ok, r.errors
    m = r.manifest
    assert (m.title, m.type, m.demo.kind.value) == ("HeatRisk EU", "data-science", "streamlit")
    assert [c.id for c in m.claims] == ["predict-2026", "city-maps"]
    assert m.claims[0].target.op.value == "abs_lte" and m.claims[1].metric is None
    assert m.problem.startswith("Each country")


def test_minimal_manifest_is_valid():
    assert parse_manifest(b"version: 1\ntitle: X\ntype: frontend\n").ok


def test_unknown_key_points_at_its_line():
    assert errs(b"version: 1\ntitle: X\ntype: frontend\ntitel: typo\n") == [
        (4, "titel", "unknown field — check the spelling")]


def test_missing_and_wrong_fields():
    out = errs(b"version: 2\ntype: backend\n")
    paths = {p: line for line, p, _ in out}
    assert paths == {"version": 1, "type": 2, "title": 1}


def test_nested_claim_errors_have_lines():
    raw = b"""version: 1
title: X
type: data-science
claims:
  - id: ok-one
    text: fine
  - id: Bad Id
    text: needs target
    metric: rmse
"""
    assert [(l, p) for l, p, _ in errs(raw)] == [(7, "claims[1].id")]
    # Cross-field rules run once the claim's own fields are valid.
    out = errs(raw.replace(b"Bad Id", b"good-id"))
    assert [(l, p) for l, p, _ in out] == [(7, "claims[1]")] and "metric" in out[0][2]


def test_target_rules():
    base = b"version: 1\ntitle: X\ntype: data-science\nclaims:\n  - id: a\n    text: t\n    metric: m\n    target: %s\n"
    assert parse_manifest(base % b"{ op: between, value: 1, value_hi: 2 }").ok
    assert "value_hi" in errs(base % b"{ op: between, value: 1 }")[0][2]
    assert "value_hi" in errs(base % b"{ op: gte, value: 1, value_hi: 2 }")[0][2]
    assert "greater" in errs(base % b"{ op: between, value: 3, value_hi: 2 }")[0][2]
    assert errs(base % b"{ op: about, value: 1 }")[0][1] == "claims[0].target.op"


def test_duplicate_claim_ids_and_yaml_keys():
    raw = b"version: 1\ntitle: X\ntitle: Y\ntype: frontend\nclaims:\n  - {id: a, text: one}\n  - {id: a, text: two}\n"
    out = errs(raw)
    assert (3, "title", "`title` appears more than once") in out
    assert any(l == 7 and "already used" in m for l, _, m in out)


def test_section_must_match_type():
    raw = b"version: 1\ntitle: X\ntype: frontend\ndata:\n  sources: []\n"
    assert errs(raw) == [(4, "data", "`data:` is for type data-science projects — this one is type frontend")]


def test_yaml_syntax_error_line():
    out = errs(b"version: 1\ntitle: X\ntype: [frontend\n")
    assert out[0][0] in (3, 4) and out[0][2].startswith("YAML syntax error")


def test_not_a_mapping_size_and_encoding():
    assert "mapping" in errs(b"- just\n- a list\n")[0][2]
    assert "larger" in errs(b"#" * (MAX_BYTES + 1))[0][2]
    assert "UTF-8" in errs(b"title: \xff\xfe")[0][2]


def test_demo_url_must_be_http():
    out = errs(b"version: 1\ntitle: X\ntype: frontend\ndemo:\n  kind: url\n  url: javascript:alert(1)\n")
    assert out[0][:2] == (6, "demo.url")
