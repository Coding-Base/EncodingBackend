# encoder/encoding_s3_utils.py
import os
import mimetypes
import logging
import time
import boto3
from botocore.config import Config
from django.conf import settings

logger = logging.getLogger(__name__)

def get_s3_client():
    """
    Create and return a boto3 S3 client using environment/settings.
    Uses signature_version='s3v4' which is broadly compatible.
    """
    # Prefer Django settings if available, fall back to environment variables
    aws_key = getattr(settings, "AWS_ACCESS_KEY_ID", os.getenv("AWS_ACCESS_KEY_ID"))
    aws_secret = getattr(settings, "AWS_SECRET_ACCESS_KEY", os.getenv("AWS_SECRET_ACCESS_KEY"))
    region = getattr(settings, "AWS_S3_REGION_NAME", os.getenv("AWS_S3_REGION_NAME", "us-east-1"))

    # Raise helpful error if credentials missing - worker should be configured with proper IAM user/role
    if not aws_key or not aws_secret:
        logger.warning("AWS credentials appear unset. Ensure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are configured.")

    session = boto3.Session(
        aws_access_key_id=aws_key,
        aws_secret_access_key=aws_secret,
        region_name=region
    )

    # Use a conservative config
    config = Config(signature_version='s3v4', retries={'max_attempts': 3})

    client = session.client('s3', config=config)
    return client


def download_file_with_retries(bucket: str, key: str, local_path: str, attempts: int = 3, delay_seconds: int = 2):
    s3 = get_s3_client()
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            logger.info(f"Downloading s3://{bucket}/{key} -> {local_path} (attempt {attempt})")
            # Ensure destination directory exists
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            s3.download_file(bucket, key, local_path)
            return True
        except Exception as exc:
            last_exc = exc
            logger.warning(f"Download attempt {attempt} failed: {exc}")
            time.sleep(delay_seconds)
    logger.error(f"Download failed after {attempts} attempts: {last_exc}")
    raise last_exc


def upload_hls_folder_to_s3(local_hls_dir: str, s3_prefix: str, bucket: str = None,
                           sse_algorithm: str = None, kms_key_id: str = None):
    """
    Upload the HLS folder (master.m3u8 + segments + thumbnails) to S3.
    Ensures ServerSideEncryption header is sent with each PutObject (complies with bucket policy).
    - local_hls_dir: local directory containing HLS output (master.m3u8, <quality>/playlist.m3u8, .ts)
    - s3_prefix: target prefix in bucket e.g. "videos/<video_id>/hls"
    - bucket: bucket name (defaults to settings.AWS_STORAGE_BUCKET_NAME)
    - sse_algorithm: 'AES256' or 'aws:kms' (defaults to AWS_S3_DEFAULT_SSE setting or 'AES256')
    - kms_key_id: optional KMS key id when using 'aws:kms'
    Returns list of uploaded keys.
    """
    bucket = bucket or getattr(settings, 'AWS_STORAGE_BUCKET_NAME', os.getenv('AWS_STORAGE_BUCKET_NAME'))
    if not bucket:
        raise ValueError("S3 bucket name not configured (AWS_STORAGE_BUCKET_NAME).")

    sse_algorithm = sse_algorithm or getattr(settings, 'AWS_S3_DEFAULT_SSE', os.getenv('AWS_S3_DEFAULT_SSE', 'AES256'))
    kms_key_id = kms_key_id or getattr(settings, 'AWS_S3_KMS_KEY_ID', os.getenv('AWS_S3_KMS_KEY_ID', None))

    s3 = get_s3_client()
    uploaded = []

    # Walk local HLS folder and upload every file preserving relative path
    for root, _, files in os.walk(local_hls_dir):
        for fname in files:
            local_path = os.path.join(root, fname)
            rel_path = os.path.relpath(local_path, local_hls_dir)
            s3_key = f"{s3_prefix.rstrip('/')}/{rel_path}".replace("\\", "/")

            # Determine content type
            content_type, _ = mimetypes.guess_type(fname)
            if content_type is None:
                if fname.endswith('.m3u8'):
                    content_type = 'application/vnd.apple.mpegurl'
                elif fname.endswith('.ts'):
                    content_type = 'video/MP2T'
                elif fname.endswith('.jpg') or fname.endswith('.jpeg'):
                    content_type = 'image/jpeg'
                else:
                    content_type = 'application/octet-stream'

            extra_args = {
                'ContentType': content_type,
                'ServerSideEncryption': sse_algorithm
            }
            if sse_algorithm == 'aws:kms' and kms_key_id:
                extra_args['SSEKMSKeyId'] = kms_key_id

            try:
                logger.info(f"Uploading {local_path} -> s3://{bucket}/{s3_key} (content-type={content_type}, sse={sse_algorithm})")
                # use upload_file which handles multipart for large files and accepts ExtraArgs
                s3.upload_file(local_path, bucket, s3_key, ExtraArgs=extra_args)
                uploaded.append(s3_key)
            except Exception as exc:
                logger.error(f"Failed to upload {local_path} to s3://{bucket}/{s3_key}: {exc}")
                # Raise so worker can mark job failed; don't swallow exception
                raise

    return uploaded
