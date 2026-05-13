import os
import asyncio
import logging
from typing import Optional
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
import mimetypes
from app.config import settings
logger = logging.getLogger(__name__)


# =========================================================
# S3 CLIENT
# =========================================================

s3_client = boto3.client(
    "s3",
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_REGION,
    config=Config(
        signature_version="s3v4",
        s3={
            "addressing_style": "virtual"
        }
    )
)

BUCKET_NAME = settings.S3_BUCKET_NAME
REGION = settings.AWS_REGION


# =========================================================
# HELPERS
# =========================================================

def normalize_s3_key(key: str) -> str:
    """
    Normalize S3 object key.
    """

    if not key:
        return ""

    key = key.replace("\\", "/")

    if key.startswith("uploads/"):
        key = key.replace("uploads/", "", 1)

    if key.startswith("/"):
        key = key[1:]

    return key


def build_s3_url(key: str) -> str:
    """
    Generate public S3 URL.
    """

    key = normalize_s3_key(key)

    return (
        f"https://{BUCKET_NAME}"
        f".s3.{REGION}.amazonaws.com/{key}"
    )


# =========================================================
# UPLOAD FILE
# =========================================================

async def upload_to_storage(
    file_path: str,
    target_name: str,
    content_type: str = "application/octet-stream"
) -> str:
    """
    Upload local file to S3.
    """

    target_name = normalize_s3_key(target_name)

    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)

    try:

        logger.info(f"Uploading file to S3: {target_name}")

        await asyncio.to_thread(
            s3_client.upload_file,
            file_path,
            BUCKET_NAME,
            target_name,
            ExtraArgs={
                "ContentType": content_type
            }
        )

        url = build_s3_url(target_name)

        logger.info(f"S3 upload success: {url}")

        return url

    except ClientError as e:

        logger.exception("S3 upload failed")

        raise Exception(
            f"Failed to upload "
            f"{file_path} -> {BUCKET_NAME}/{target_name}: {str(e)}"
        )


# =========================================================
# UPLOAD BYTES
# =========================================================

async def upload_bytes_to_storage(
    file_bytes: bytes,
    target_name: str,
    content_type: str = "application/octet-stream"
) -> str:
    """
    Upload raw bytes to S3.
    """

    target_name = normalize_s3_key(target_name)

    try:

        logger.info(f"Uploading bytes to S3: {target_name}")

        await asyncio.to_thread(
            s3_client.put_object,
            Bucket=BUCKET_NAME,
            Key=target_name,
            Body=file_bytes,
            ContentType=content_type
        )

        url = build_s3_url(target_name)

        logger.info(f"S3 bytes upload success: {url}")

        return url

    except ClientError as e:

        logger.exception("S3 byte upload failed")

        raise Exception(
            f"Failed to upload bytes "
            f"to {BUCKET_NAME}/{target_name}: {str(e)}"
        )


# =========================================================
# DOWNLOAD FILE BYTES
# =========================================================

async def get_file_from_storage(target_name: str) -> Optional[bytes]:
    """
    Download file from S3 as bytes.
    """

    target_name = normalize_s3_key(target_name)

    try:

        logger.info(f"Downloading from S3: {target_name}")

        response = await asyncio.to_thread(
            s3_client.get_object,
            Bucket=BUCKET_NAME,
            Key=target_name
        )

        data = response["Body"].read()

        logger.info(f"S3 download success: {target_name}")

        return data

    except ClientError as e:

        logger.exception("S3 download failed")

        return None


# =========================================================
# DOWNLOAD FILE TO LOCAL PATH
# =========================================================

async def download_file_from_storage(
    target_name: str,
    local_path: str
) -> str:
    """
    Download S3 file to local filesystem.
    """

    target_name = normalize_s3_key(target_name)

    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    try:

        logger.info(f"Downloading S3 file: {target_name}")

        await asyncio.to_thread(
            s3_client.download_file,
            BUCKET_NAME,
            target_name,
            local_path
        )

        logger.info(f"Downloaded to: {local_path}")

        return local_path

    except ClientError as e:

        logger.exception("S3 local download failed")

        raise Exception(
            f"Failed downloading "
            f"{BUCKET_NAME}/{target_name}: {str(e)}"
        )


# =========================================================
# DELETE FILE
# =========================================================

async def delete_from_storage(target_name: str) -> bool:
    """
    Delete file from S3.
    """

    target_name = normalize_s3_key(target_name)

    try:

        logger.info(f"Deleting S3 object: {target_name}")

        await asyncio.to_thread(
            s3_client.delete_object,
            Bucket=BUCKET_NAME,
            Key=target_name
        )

        logger.info(f"S3 delete success: {target_name}")

        return True

    except ClientError as e:

        logger.exception("S3 delete failed")

        return False


# =========================================================
# CHECK IF FILE EXISTS
# =========================================================

async def file_exists(target_name: str) -> bool:
    """
    Check if S3 object exists.
    """

    target_name = normalize_s3_key(target_name)

    try:

        await asyncio.to_thread(
            s3_client.head_object,
            Bucket=BUCKET_NAME,
            Key=target_name
        )

        return True

    except ClientError:

        return False


# =========================================================
# GENERATE PRESIGNED URL
# =========================================================

def generate_presigned_url(
    target_name: str,
    expiration: int = 3600
) -> Optional[str]:
    """
    Generate temporary access URL.
    """

    target_name = normalize_s3_key(target_name)

    try:

        content_type, _ = mimetypes.guess_type(target_name)
        
        params = {
            "Bucket": BUCKET_NAME,
            "Key": target_name,
            "ResponseContentDisposition": "inline"
        }
        
        if content_type:
            params["ResponseContentType"] = content_type

        url = s3_client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expiration
        )

        return url

    except ClientError as e:

        logger.exception("Presigned URL generation failed")

        return None


# =========================================================
# LIST FILES
# =========================================================

async def list_storage_files(prefix: str = "") -> list:
    """
    List files in S3 bucket.
    """

    prefix = normalize_s3_key(prefix)

    try:

        response = await asyncio.to_thread(
            s3_client.list_objects_v2,
            Bucket=BUCKET_NAME,
            Prefix=prefix
        )

        contents = response.get("Contents", [])

        return [
            {
                "key": item["Key"],
                "size": item["Size"],
                "last_modified": item["LastModified"].isoformat(),
                "url": build_s3_url(item["Key"])
            }
            for item in contents
        ]

    except ClientError as e:

        logger.exception("S3 list failed")

        return []


# =========================================================
# COPY FILE
# =========================================================

async def copy_storage_file(
    source_key: str,
    destination_key: str
) -> bool:
    """
    Copy file inside S3 bucket.
    """

    source_key = normalize_s3_key(source_key)
    destination_key = normalize_s3_key(destination_key)

    try:

        copy_source = {
            "Bucket": BUCKET_NAME,
            "Key": source_key
        }

        await asyncio.to_thread(
            s3_client.copy_object,
            Bucket=BUCKET_NAME,
            CopySource=copy_source,
            Key=destination_key
        )

        return True

    except ClientError as e:

        logger.exception("S3 copy failed")

        return False


# =========================================================
# EXTRACT S3 KEY FROM URL
# =========================================================

def get_storage_key_from_url(url: str) -> str:
    """
    Extract S3 object key from URL.
    """

    if not url:
        return ""

    if ".amazonaws.com/" in url:
        key = url.split(".amazonaws.com/")[1]
    else:
        key = url

    return normalize_s3_key(key)


# =========================================================
# ALIASES
# =========================================================

upload_to_s3 = upload_to_storage
upload_bytes_to_s3 = upload_bytes_to_storage
get_file_from_s3 = get_file_from_storage
delete_from_s3 = delete_from_storage
get_s3_key_from_url = get_storage_key_from_url