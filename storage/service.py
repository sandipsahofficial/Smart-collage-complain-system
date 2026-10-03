import io
import mimetypes
import os
import uuid
from pathlib import Path
from typing import IO

from werkzeug.utils import secure_filename


class StorageService:
    provider = 'abstract'

    def save_upload(self, file_obj: IO[bytes], original_name: str, content_type: str | None = None, prefix: str = 'complaints'):
        raise NotImplementedError

    def public_url(self, storage_key: str) -> str:
        raise NotImplementedError

    def private_url(self, storage_key: str, expires_in: int = 300) -> str:
        raise NotImplementedError

    def read_upload(self, storage_key: str) -> bytes | None:
        raise NotImplementedError

    def delete(self, storage_key: str) -> bool:
        raise NotImplementedError

    def validate_storage_key(self, storage_key: str) -> bool:
        if not storage_key:
            return False
        normalized = str(storage_key).replace('\\', '/').strip('/')
        parts = normalized.split('/')
        return bool(parts) and all(part not in {'', '.', '..'} and secure_filename(part) == part for part in parts)


class LocalStorageService(StorageService):
    provider = 'local'

    def __init__(self):
        self.base_dir = os.path.abspath(os.path.join(os.getcwd(), 'instance', 'uploads'))
        os.makedirs(self.base_dir, exist_ok=True)

    def save_upload(self, file_obj: IO[bytes], original_name: str, content_type: str | None = None, prefix: str = 'complaints'):
        file_obj.seek(0)
        payload = file_obj.read()
        suffix = Path(str(original_name or 'upload')).suffix.lower()
        if not suffix:
            suffix = '.bin'
        storage_key = f"{uuid.uuid4().hex}{suffix}"
        target_path = os.path.join(self.base_dir, storage_key)
        with open(target_path, 'wb') as handle:
            handle.write(payload)
        return {
            'storage_key': storage_key,
            'original_name': secure_filename(str(original_name) or 'upload'),
            'mime_type': content_type or 'application/octet-stream',
            'size': len(payload),
            'provider': self.provider,
            'public_url': f'/uploads/{storage_key}',
        }

    def public_url(self, storage_key: str) -> str:
        return self.private_url(storage_key)

    def private_url(self, storage_key: str, expires_in: int = 300) -> str:
        if not self.validate_storage_key(storage_key):
            return ''
        return f'/uploads/{secure_filename(storage_key.replace(chr(92), "/").split("/")[-1])}'

    def read_upload(self, storage_key: str) -> bytes | None:
        if not self.validate_storage_key(storage_key):
            return None
        target_path = os.path.join(self.base_dir, *storage_key.replace('\\', '/').split('/'))
        try:
            with open(target_path, 'rb') as handle:
                return handle.read()
        except OSError:
            return None

    def delete(self, storage_key: str) -> bool:
        if not storage_key:
            return False
        safe_key = secure_filename(storage_key.replace('\\', '/').split('/')[-1])
        target_path = os.path.join(self.base_dir, safe_key)
        if os.path.exists(target_path):
            os.remove(target_path)
            return True
        return False


class S3StorageService(StorageService):
    provider = 's3'

    def __init__(self):
        self.bucket = os.getenv('STORAGE_BUCKET') or os.getenv('S3_BUCKET')
        self.region = os.getenv('STORAGE_REGION') or os.getenv('S3_REGION', 'us-east-1')
        self.prefix = os.getenv('STORAGE_PREFIX') or os.getenv('S3_PREFIX', 'complaint-files')

    def save_upload(self, file_obj: IO[bytes], original_name: str, content_type: str | None = None, prefix: str = 'complaints'):
        import boto3

        if not self.bucket:
            raise ValueError('Storage bucket is not configured.')

        file_obj.seek(0)
        payload = file_obj.read()
        storage_key = f"{self.prefix.strip('/')}/{prefix}/{uuid.uuid4().hex}{Path(str(original_name or 'upload')).suffix.lower()}"
        key = storage_key.lstrip('/')
        boto3.client('s3', region_name=self.region).put_object(
            Bucket=self.bucket,
            Key=key,
            Body=payload,
            ContentType=content_type or 'application/octet-stream',
        )
        return {
            'storage_key': key,
            'original_name': secure_filename(str(original_name) or 'upload'),
            'mime_type': content_type or 'application/octet-stream',
            'size': len(payload),
            'provider': self.provider,
            'public_url': f'https://{self.bucket}.s3.{self.region}.amazonaws.com/{key}',
        }

    def public_url(self, storage_key: str) -> str:
        return self.private_url(storage_key)

    def private_url(self, storage_key: str, expires_in: int = 300) -> str:
        if not self.bucket or not self.validate_storage_key(storage_key):
            return ''
        import boto3

        return boto3.client('s3', region_name=self.region).generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket, 'Key': storage_key.lstrip('/')},
            ExpiresIn=expires_in,
        )

    def read_upload(self, storage_key: str) -> bytes | None:
        if not self.bucket or not self.validate_storage_key(storage_key):
            return None
        import boto3

        try:
            response = boto3.client('s3', region_name=self.region).get_object(
                Bucket=self.bucket, Key=storage_key.lstrip('/')
            )
            return response['Body'].read()
        except Exception:
            return None

    def delete(self, storage_key: str) -> bool:
        if not self.bucket or not storage_key:
            return False
        import boto3

        try:
            boto3.client('s3', region_name=self.region).delete_object(Bucket=self.bucket, Key=storage_key.lstrip('/'))
            return True
        except Exception:
            return False


def get_storage_service() -> StorageService:
    provider = (os.getenv('STORAGE_PROVIDER') or ('s3' if os.getenv('STORAGE_BUCKET') or os.getenv('S3_BUCKET') else 'local')).lower()
    if provider == 's3':
        return S3StorageService()
    return LocalStorageService()


storage_service = get_storage_service()
