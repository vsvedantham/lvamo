import boto3
from botocore.config import Config

from app.config import settings


def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def upload_file(key: str, data: bytes, content_type: str) -> None:
    client = get_r2_client()
    client.put_object(
        Bucket=settings.r2_bucket_name,
        Key=key,
        Body=data,
        ContentType=content_type,
    )


def delete_file(key: str) -> None:
    client = get_r2_client()
    client.delete_object(Bucket=settings.r2_bucket_name, Key=key)


def generate_presigned_url(key: str, expires_in: int = 300, download_name: str | None = None) -> str:
    """A short-lived signed GET URL for an object that isn't otherwise
    public — R2 buckets in this project aren't. Callers own their own
    authorization check (is this caller allowed to see this specific
    object?) before calling this; it does no such check itself."""
    client = get_r2_client()
    params = {"Bucket": settings.r2_bucket_name, "Key": key}
    if download_name:
        # Save under a readable name; the browser still opens PDFs inline.
        params["ResponseContentDisposition"] = f'inline; filename="{download_name}"'
    return client.generate_presigned_url("get_object", Params=params, ExpiresIn=expires_in)
