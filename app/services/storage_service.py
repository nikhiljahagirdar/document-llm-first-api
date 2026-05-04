import boto3
import asyncio
from botocore.exceptions import ClientError
from botocore.config import Config
from app.config import settings

# Create S3 client using centralized settings
s3_client = boto3.client(
    's3',
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_REGION,
    config=Config(signature_version='s3v4')
)

async def upload_to_storage(file_path: str, target_name: str) -> str:
    """
    Uploads a file to S3 bucket.
    """
    # Normalize key for S3 (must use / and no local prefixes like uploads\)
    target_name = target_name.replace("\\", "/")
    if target_name.startswith("uploads/"):
        target_name = target_name.replace("uploads/", "", 1)

    try:
        # Run synchronous boto3 call in a separate thread
        await asyncio.to_thread(
            s3_client.upload_file,
            file_path,
            settings.S3_BUCKET_NAME,
            target_name,
            ExtraArgs={'ACL': 'public-read'}
        )
        url = f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{target_name}"
        return url
    except ClientError as e:
        print(f"S3 upload failed: {e}")
        return file_path

async def upload_bytes_to_storage(image_bytes: bytes, target_name: str, content_type: str = "image/png") -> str:
    """
    Saves raw bytes (e.g. from AI image gen) to S3.
    """
    target_name = target_name.replace("\\", "/")
    if target_name.startswith("uploads/"):
        target_name = target_name.replace("uploads/", "", 1)

    try:
        await asyncio.to_thread(
            s3_client.put_object,
            Bucket=settings.S3_BUCKET_NAME,
            Key=target_name,
            Body=image_bytes,
            ContentType=content_type,
            ACL='public-read'
        )
        url = f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{target_name}"
        return url
    except ClientError as e:
        print(f"Failed to save bytes to S3: {e}")
        return None

async def get_file_from_storage(target_name: str) -> bytes:
    """
    Fetches raw bytes of a file from S3.
    """
    target_name = target_name.replace("\\", "/")
    if target_name.startswith("uploads/"):
        target_name = target_name.replace("uploads/", "", 1)

    try:
        response = await asyncio.to_thread(
            s3_client.get_object,
            Bucket=settings.S3_BUCKET_NAME,
            Key=target_name
        )
        return response['Body'].read()
    except ClientError as e:
        print(f"Failed to read file from S3: {e}")
        return None

def get_storage_key_from_url(url: str) -> str:
    """
    Extracts the S3 key from the full S3 URL and normalizes it.
    """
    if not url:
        return ""
    
    # Assuming URL format: https://bucket.s3.region.amazonaws.com/key
    if ".amazonaws.com/" in url:
        key = url.split(".amazonaws.com/")[1]
    else:
        key = url
    
    # Standardize to forward slashes
    key = key.replace("\\", "/")
    
    # Critical: Strip "uploads/" if it's still there (leftover from local paths)
    if key.startswith("uploads/"):
        key = key.replace("uploads/", "", 1)
        
    return key

# Compatibility aliases for old S3 function names
upload_to_s3 = upload_to_storage
upload_bytes_to_s3 = upload_bytes_to_storage
get_file_from_s3 = get_file_from_storage
get_s3_key_from_url = get_storage_key_from_url

def generate_presigned_url(target_name: str, expiration: int = 3600) -> str:
    """
    Generate a presigned URL to share an S3 object.
    """
    # Normalize key before signing
    target_name = target_name.replace("\\", "/")
    if target_name.startswith("uploads/"):
        target_name = target_name.replace("uploads/", "", 1)

    try:
        response = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.S3_BUCKET_NAME, 'Key': target_name},
            ExpiresIn=expiration
        )
        return response
    except ClientError as e:
        print(f"Failed to generate presigned URL: {e}")
        return None
