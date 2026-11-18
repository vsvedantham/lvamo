# Role synonyms — expand target role matching beyond exact title.
# Shared between discovery-time filtering (app/discovery/location.py) and
# scoring (app/scoring/rule_based.py) so a job title that only matches via
# synonym still gets fetched, not just scored.
ROLE_SYNONYMS: dict[str, list[str]] = {
    "data engineer": ["data engineer", "analytics engineer", "etl developer", "pipeline engineer",
                      "big data engineer", "data platform engineer", "data infrastructure",
                      "data engineering", "data integration engineer", "data warehouse engineer",
                      "dwh engineer", "dwh developer", "etl engineer", "elt engineer", "big data developer",
                      "dataops", "data ops engineer", "analytics developer", "bi engineer", "bi developer",
                      "data warehouse developer", "datenengineer", "data-engineer", "dateningenieur",
                      "databricks engineer", "databricks developer", "spark engineer", "spark developer"],
    "data scientist": ["data scientist", "ml engineer", "machine learning engineer",
                       "ai engineer", "research scientist", "applied scientist"],
    "data analyst": ["data analyst", "business analyst", "analytics analyst",
                     "reporting analyst", "bi analyst", "business intelligence analyst"],
    "software engineer": ["software engineer", "software developer", "backend engineer",
                          "backend developer", "full stack", "fullstack", "application developer"],
    "frontend engineer": ["frontend engineer", "frontend developer", "ui engineer",
                          "web developer", "react developer", "javascript developer"],
    "devops engineer": ["devops engineer", "site reliability", "sre", "platform engineer",
                        "infrastructure engineer", "cloud engineer", "devsecops"],
    "product manager": ["product manager", "product owner", "program manager", "technical pm"],
    "data architect": ["data architect", "solution architect", "enterprise architect",
                       "cloud architect", "database architect"],
}


def expand_role(role: str) -> list[str]:
    """Return all synonyms for a role including the role itself."""
    role_lower = role.lower()
    for canonical, synonyms in ROLE_SYNONYMS.items():
        if role_lower in synonyms or canonical in role_lower or role_lower in canonical:
            return synonyms
    return [role_lower]
