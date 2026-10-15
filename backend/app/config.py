from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database
    database_url: str

    # JWT
    secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Cloudflare R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = ""
    r2_public_url: str = ""

    # AI providers
    openai_api_key: str = ""

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # Jobref — LinkedIn OAuth (registration identity source)
    jobref_linkedin_client_id: str = ""
    jobref_linkedin_client_secret: str = ""
    jobref_linkedin_redirect_uri: str = "http://localhost:8000/api/v1/jobref/auth/linkedin/callback"

    # ProSho — one GitHub App for sign-in (user OAuth), reading prosho.yaml
    # (installation tokens) and push webhooks. The private key is the App's
    # PEM, base64-encoded onto one line so it fits in an env file.
    prosho_github_app_id: str = ""
    prosho_github_app_slug: str = ""
    prosho_github_client_id: str = ""
    prosho_github_client_secret: str = ""
    prosho_github_private_key_b64: str = ""
    prosho_github_webhook_secret: str = ""
    prosho_github_redirect_uri: str = "http://localhost:8000/api/v1/prosho/auth/github/callback"
    # Closed beta: GitHub logins (comma-separated) allowed to create a ProSho
    # account. Existing accounts can always sign in. Empty = nobody new.
    prosho_signup_allowlist: str = ""

    # Server
    backend_cors_origins: List[str] = ["http://localhost:5173"]
    backend_port: int = 8000
    frontend_base_url: str = "http://localhost:5173"

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip().strip("[]")
            return [u.strip().strip('"').strip("'") for u in v.split(",") if u.strip()]
        return v


settings = Settings()
