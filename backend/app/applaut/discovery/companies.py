import json
from pathlib import Path

from app.applaut.discovery.adapters.ashby import AshbyAdapter
from app.applaut.discovery.adapters.greenhouse import GreenhouseAdapter
from app.applaut.discovery.adapters.lever import LeverAdapter
from app.applaut.discovery.adapters.personio import PersonioAdapter
from app.applaut.discovery.adapters.recruitee import RecruiteeAdapter
from app.applaut.discovery.adapters.smartrecruiters import SmartRecruitersAdapter
from app.applaut.discovery.adapters.workable import WorkableAdapter
from app.applaut.discovery.base import JobSourceAdapter

# Keyed by each adapter's source_name — reused by
# scripts/discover_company_slugs.py so endpoint knowledge stays inside
# adapters rather than being duplicated in the probing script.
ADAPTER_REGISTRY: dict[str, JobSourceAdapter] = {
    "greenhouse": GreenhouseAdapter(),
    "lever": LeverAdapter(),
    "ashby": AshbyAdapter(),
    "personio": PersonioAdapter(),
    "workable": WorkableAdapter(),
    "smartrecruiters": SmartRecruitersAdapter(),
    "recruitee": RecruiteeAdapter(),
}

# (adapter_instance, company_slug)
# Remote jobs are included when no explicit non-target country is in the location.
CURATED_BOARDS: list[tuple[JobSourceAdapter, str]] = [
    # --- Greenhouse: EU-headquartered or EU-office companies ---
    (ADAPTER_REGISTRY["greenhouse"], "celonis"),        # Munich, Germany — process mining
    (ADAPTER_REGISTRY["greenhouse"], "sumup"),          # Berlin, Germany — fintech
    (ADAPTER_REGISTRY["greenhouse"], "getyourguide"),   # Berlin, Germany — travel tech
    (ADAPTER_REGISTRY["greenhouse"], "hellofresh"),     # Berlin, Germany — food tech
    (ADAPTER_REGISTRY["greenhouse"], "adyen"),          # Amsterdam, NL — payments
    (ADAPTER_REGISTRY["greenhouse"], "intercom"),       # Dublin, IE — customer comms
    (ADAPTER_REGISTRY["greenhouse"], "elastic"),        # distributed / EU-remote
    (ADAPTER_REGISTRY["greenhouse"], "contentful"),     # Berlin, Germany — CMS
    (ADAPTER_REGISTRY["greenhouse"], "datadog"),        # EU-remote roles
    (ADAPTER_REGISTRY["greenhouse"], "mongodb"),        # EU-remote roles
    (ADAPTER_REGISTRY["greenhouse"], "twilio"),         # EU-remote roles
    (ADAPTER_REGISTRY["greenhouse"], "cloudflare"),     # EU-remote roles
    (ADAPTER_REGISTRY["greenhouse"], "okta"),           # EU offices
    (ADAPTER_REGISTRY["greenhouse"], "figma"),          # EU-remote roles
    (ADAPTER_REGISTRY["greenhouse"], "stripe"),         # Dublin, IE office
    (ADAPTER_REGISTRY["greenhouse"], "asana"),          # EU-remote roles
    # --- Lever ---
    (ADAPTER_REGISTRY["lever"], "spotify"),             # Stockholm, Sweden
    # --- Personio: DACH companies ---
    (ADAPTER_REGISTRY["personio"], "flixbus"),
    (ADAPTER_REGISTRY["personio"], "westwing"),
    # --- Workable ---
    (ADAPTER_REGISTRY["workable"], "alcemy"),           # Berlin, Germany — construction-tech / data engineering
    # --- SmartRecruiters ---
    (ADAPTER_REGISTRY["smartrecruiters"], "BoschGroup"),  # Germany — large enterprise, thousands of postings
    # --- Recruitee ---
    (ADAPTER_REGISTRY["recruitee"], "xite"),            # Amsterdam, Netherlands — media tech
]


# (source, slug) → the company's name as written ("MaibornWolff"), from company_boards.json.
BOARD_NAMES: dict[tuple[str, str], str] = {}


def _load_scripted_boards() -> list[tuple[JobSourceAdapter, str]]:
    """Load companies discovered by scripts/discover_company_slugs.py.

    Skips any (adapter, slug) pair already present in CURATED_BOARDS so a
    company doesn't get fetched twice per discovery run.
    """
    data_path = Path(__file__).parent / "data" / "company_boards.json"
    if not data_path.exists():
        return []
    curated_keys = {(adapter.source_name, slug.lower()) for adapter, slug in CURATED_BOARDS}
    entries = json.loads(data_path.read_text(encoding="utf-8"))
    boards = []
    for entry in entries:
        if entry.get("name"):
            BOARD_NAMES[(entry["adapter"], entry["slug"].lower())] = entry["name"]
        adapter = ADAPTER_REGISTRY.get(entry["adapter"])
        if adapter is None:
            continue
        if (entry["adapter"], entry["slug"].lower()) in curated_keys:
            continue
        boards.append((adapter, entry["slug"]))
    return boards


COMPANY_BOARDS: list[tuple[JobSourceAdapter, str]] = CURATED_BOARDS + _load_scripted_boards()
