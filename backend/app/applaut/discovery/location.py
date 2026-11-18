import re

from app.applaut.core.role_synonyms import expand_role

COUNTRY_KEYWORDS: dict[str, list[str]] = {
    "DE": ["germany", "deutschland", "berlin", "munich", "münchen", "hamburg", "frankfurt",
           "cologne", "köln", "düsseldorf", "stuttgart", "leipzig", "dortmund", "essen",
           "Bremen", "bremen", "hannover", "nuremberg", "nürnberg"],
    "FR": ["france", "paris", "lyon", "marseille", "toulouse", "nice", "nantes", "bordeaux",
           "strasbourg", "lille", "rennes", "grenoble"],
    "NL": ["netherlands", "holland", "amsterdam", "rotterdam", "the hague", "den haag",
           "utrecht", "eindhoven", "tilburg", "groningen"],
    "AT": ["austria", "österreich", "vienna", "wien", "graz", "linz", "salzburg", "innsbruck"],
    "BE": ["belgium", "belgique", "brussels", "bruxelles", "antwerp", "antwerpen", "ghent",
           "gent", "bruges", "brugge", "liège"],
    "CH": ["switzerland", "schweiz", "suisse", "zurich", "zürich", "geneva", "genève",
           "basel", "bern", "lausanne"],
    "ES": ["spain", "españa", "madrid", "barcelona", "valencia", "seville", "sevilla",
           "bilbao", "málaga", "malaga", "zaragoza"],
    "IT": ["italy", "italia", "rome", "roma", "milan", "milano", "naples", "napoli",
           "turin", "torino", "florence", "firenze", "bologna"],
    "PT": ["portugal", "lisbon", "lisboa", "porto", "braga", "coimbra", "faro"],
    "PL": ["poland", "polska", "warsaw", "warszawa", "kraków", "krakow", "wrocław",
           "wroclaw", "gdańsk", "gdansk", "poznań", "poznan", "łódź", "lodz"],
    "SE": ["sweden", "sverige", "stockholm", "gothenburg", "göteborg", "malmö", "malmo",
           "uppsala", "linköping"],
    "NO": ["norway", "norge", "oslo", "bergen", "trondheim", "stavanger"],
    "DK": ["denmark", "danmark", "copenhagen", "københavn", "aarhus", "odense"],
    "FI": ["finland", "suomi", "helsinki", "espoo", "tampere", "oulu", "turku"],
    "IE": ["ireland", "éire", "dublin", "cork", "limerick", "galway"],
    "CZ": ["czech", "czechia", "prague", "praha", "brno", "ostrava", "plzeň"],
    "RO": ["romania", "românia", "bucharest", "bucurești", "cluj", "timișoara"],
    "HU": ["hungary", "magyarország", "budapest", "debrecen", "pécs", "miskolc"],
    "GB": ["united kingdom", " uk", "uk)", "(uk", "england", "scotland", "wales", "london", "manchester",
           "edinburgh", "birmingham", "glasgow", "bristol", "leeds", "cambridge, uk", "oxford, uk"],
    "IN": ["india", "bangalore", "bengaluru", "hyderabad", "pune", "chennai", "mumbai", "gurgaon", "noida"],
    "CA": ["canada", "toronto", "vancouver", "montreal", "montréal"],
    "AU": ["australia", "sydney", "melbourne", "brisbane"],
    "SG": ["singapore"],
    "AE": ["united arab emirates", "dubai", "abu dhabi"],
    "IL": ["israel", "tel aviv"],
    "BR": ["brazil", "brasil", "são paulo", "sao paulo"],
    "LU": ["luxembourg", "luxemburg"],
    "GR": ["greece", "athens"],
    "BG": ["bulgaria", "sofia"],
    "RS": ["serbia", "belgrade"],
    "HR": ["croatia", "zagreb"],
    "SK": ["slovakia", "bratislava"],
    "SI": ["slovenia", "ljubljana"],
    "LT": ["lithuania", "vilnius"],
    "LV": ["latvia", "riga"],
    "EE": ["estonia", "tallinn"],
    "UA": ["ukraine", "kyiv", "kiev", "lviv"],
    "MK": ["north macedonia", "macedonia", "skopje"],
    "AL": ["albania", "tirana"],
    "BA": ["bosnia", "sarajevo"],
    "TR": ["turkey", "türkiye", "istanbul"],
    "CY": ["cyprus", "limassol", "nicosia"],
    "MT": ["malta"],
    "GE": ["tbilisi"],
    "AM": ["armenia", "yerevan"],
    "MX": ["mexico", "méxico"],
    "AR": ["argentina", "buenos aires"],
    "CO": ["colombia", "bogotá", "bogota"],
    "JP": ["japan", "tokyo"],
    "CN": ["china", "shanghai", "beijing", "shenzhen"],
    "KR": ["korea", "seoul"],
    "PH": ["philippines", "manila"],
    "ZA": ["south africa", "cape town", "johannesburg"],
    "EG": ["egypt", "cairo"],
    "PK": ["pakistan", "lahore", "karachi"],
    "US": ["united states", "usa", "u.s.", "new york", "san francisco", "seattle",
           "chicago", "boston", "austin", "los angeles", "denver", "atlanta",
           "remote us", "us remote", "anywhere in the us", "remote - us", "remote - usa",
           "north america", "remote (north america)", "remote (us"],
}

REMOTE_KEYWORDS = [
    "remote", "anywhere", "distributed", "work from home", "wfh", "fully remote",
    "worldwide", "global", "emea", "apac", "latam",
]
HYBRID_KEYWORDS = ["hybrid"]


def resolve_country(location: str | None) -> str | None:
    if not location:
        return None
    loc = location.lower()
    for code, keywords in COUNTRY_KEYWORDS.items():
        if any(kw in loc for kw in keywords):
            return code
    return None


def resolve_remote_option(location: str | None, description: str | None = None) -> str | None:
    text = f"{location or ''} {description or ''}".lower()
    if any(kw in text for kw in REMOTE_KEYWORDS):
        return "remote"
    if any(kw in text for kw in HYBRID_KEYWORDS):
        return "hybrid"
    return "onsite"


def matches_countries(country_code: str | None, target_countries: list[str]) -> bool:
    if not country_code:
        return False
    return country_code in target_countries


# Student and trainee postings: never a match unless a target role asks for one.
STUDENT_WORDS = ("werkstudent", "working student", "praktikum", "praktikant", "internship", "intern ",
                 "intern)", "intern,", "(intern", "- intern", "ausbildung", "azubi", "minijob", "trainee",
                 "studentische", "student assistant", "student job", "abschlussarbeit", "masterarbeit",
                 "bachelorarbeit", "thesis", "duales studium", "dual study", "dualer student")
# Too common to find jobs by on their own (every developer job names them): a
# title is matched, and the job boards searched, by the user's other skills.
GENERIC_SKILLS = {"python", "sql", "java", "javascript", "typescript", "c#", "c++", "go", "docker", "git", "linux",
                  "excel", "html", "css", "react", "rest apis", "english", "german", "microsoft azure", "azure",
                  "aws", "gcp", "kubernetes", "agile", "scrum", "jira", "fastapi", "postgresql", "nginx",
                  "sqlalchemy", "alembic", "openai apis", "cloudflare r2"}
# A skill in a title only counts with one of these ("Databricks Engineer", not "Databricks Sales").
ROLE_WORDS = re.compile(r"engineer|developer|entwickler|ingenieur|programmer|programmierer|architect|consultant"
                        r"|berater|specialist|spezialist", re.I)


def is_student_role(title: str) -> bool:
    t = f" {title.lower()} "
    return any(w in t for w in STUDENT_WORDS)


def _skill_in(skill: str, title: str) -> bool:
    return bool(re.search(r"(?<![\w#+.])" + re.escape(skill) + r"(?![\w#+])", title, re.I))


def matches_roles(title: str, target_roles: list[str], skills: list[str] | tuple = ()) -> bool:
    """A target role (or one of its related titles) in the title; or one of the
    user's skills together with a role word ("PySpark Developer"). Student and
    trainee postings never match unless a target role asks for one."""
    title_lower = title.lower()
    if is_student_role(title) and not any(is_student_role(r) for r in target_roles):
        return False
    for role in target_roles:
        if role.lower() in title_lower:
            return True
        if any(syn in title_lower for syn in expand_role(role)):
            return True
    if skills and ROLE_WORDS.search(title):
        return any(_skill_in(s, title) for s in skills if len(s) >= 3 and s.lower() not in GENERIC_SKILLS)
    return False


def wanted_place(country_code: str | None, remote_option: str | None, target_countries: list[str]) -> bool:
    """In a target country, or remote with no country named."""
    if country_code:
        return country_code in target_countries
    return remote_option == "remote"


_LEGAL = re.compile(r"\b(gmbh|ag|se|kg|kgaa|mbh|ug|ltd|limited|inc|llc|bv|b\.v|nv|sa|sas|oy|ab|co|plc|corp|group|"
                    r"gruppe|holding|deutschland|germany)\b\.?", re.I)
_GENDER = re.compile(r"\((?:[mwfdxi*/ ]|all genders?|alle geschlechter|gn)+\)|\b[mwfd]/[mwfd](?:/[mwfdx])?\b|\*in\b", re.I)


def dedupe_key(company: str, title: str) -> tuple[str, str]:
    """("maibornwolff", "senior data engineer") for MaibornWolff GmbH's
    "Senior Data Engineer (m/w/d)": the same job posted per city, or on
    several sites, has one key."""
    c = re.sub(r"[^a-z0-9]", "", _LEGAL.sub(" ", company.lower().replace("&", " ")))
    t = " ".join(re.sub(r"[^\w+#]+", " ", _GENDER.sub(" ", title.lower())).split())
    return c, t
