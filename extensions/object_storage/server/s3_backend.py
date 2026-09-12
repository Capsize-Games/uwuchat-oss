"""S3 (and S3-compatible) storage backend for the object_storage extension.

``boto3`` is imported lazily so the dependency is only required where the
extension is actually enabled (production); dev installs need not carry it.
"""

from __future__ import annotations

import os
from typing import Optional

from airunner_services.storage.backends import StorageBackend


class S3StorageBackend(StorageBackend):
    """Store objects in an S3 bucket (or S3-compatible endpoint).

    Configuration (env):
      AIRUNNER_S3_BUCKET        required — target bucket
      AIRUNNER_S3_REGION        optional — AWS region
      AIRUNNER_S3_ENDPOINT_URL  optional — for MinIO / R2 / other S3-compatible
      AIRUNNER_S3_PREFIX        optional — key prefix prepended to every key
    Credentials use the standard AWS resolution chain (env vars, shared
    config, or instance/IRSA role) — never hard-coded.
    """

    def __init__(
        self,
        bucket: str,
        *,
        region: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        prefix: str = "",
    ) -> None:
        if not bucket:
            raise ValueError("S3StorageBackend requires a bucket name")
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._region = region
        self._endpoint_url = endpoint_url
        self._client = None

    # -- boto3 client (lazy) ------------------------------------------------
    @property
    def client(self):
        if self._client is None:
            import boto3  # lazy: only needed when the extension is enabled

            self._client = boto3.client(
                "s3",
                region_name=self._region,
                endpoint_url=self._endpoint_url,
            )
        return self._client

    def _full_key(self, key: str) -> str:
        key = key.lstrip("/")
        return f"{self._prefix}/{key}" if self._prefix else key

    # -- StorageBackend interface ------------------------------------------
    def save(
        self,
        key: str,
        data: bytes,
        *,
        content_type: Optional[str] = None,
    ) -> str:
        extra = {"ContentType": content_type} if content_type else {}
        self.client.put_object(
            Bucket=self._bucket,
            Key=self._full_key(key),
            Body=data,
            **extra,
        )
        return key

    def open(self, key: str) -> bytes:
        resp = self.client.get_object(
            Bucket=self._bucket, Key=self._full_key(key)
        )
        return resp["Body"].read()

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(
                Bucket=self._bucket, Key=self._full_key(key)
            )
            return True
        except ClientError:
            return False

    def delete(self, key: str) -> None:
        self.client.delete_object(
            Bucket=self._bucket, Key=self._full_key(key)
        )

    def delete_prefix(self, prefix: str) -> int:
        """Delete every object whose S3 key starts with *prefix*.

        Uses ``list_objects_v2`` with 1000-object pages
        and ``delete_objects`` for batch deletion.
        Returns the number of objects deleted.
        """
        full_prefix = self._full_key(prefix)
        count = 0
        paginator = self.client.get_paginator("list_objects_v2")
        pages = paginator.paginate(
            Bucket=self._bucket, Prefix=full_prefix,
        )
        for page in pages:
            contents = page.get("Contents") or []
            if not contents:
                continue
            objects = [{"Key": obj["Key"]} for obj in contents]
            self.client.delete_objects(
                Bucket=self._bucket,
                Delete={"Objects": objects, "Quiet": True},
            )
            count += len(objects)
        return count

    def url(self, key: str, *, expires: int = 3600) -> Optional[str]:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": self._full_key(key)},
            ExpiresIn=expires,
        )

    # Object storage has no local filesystem path.
    def local_path(self, key: str) -> Optional[str]:
        return None


def build_s3_backend_from_env() -> Optional[S3StorageBackend]:
    """Construct an S3 backend from env, or None if no bucket is configured."""
    bucket = (os.environ.get("AIRUNNER_S3_BUCKET") or "").strip()
    if not bucket:
        return None
    return S3StorageBackend(
        bucket,
        region=(os.environ.get("AIRUNNER_S3_REGION") or "").strip() or None,
        endpoint_url=(
            (os.environ.get("AIRUNNER_S3_ENDPOINT_URL") or "").strip() or None
        ),
        prefix=(os.environ.get("AIRUNNER_S3_PREFIX") or "").strip(),
    )


__all__ = ["S3StorageBackend", "build_s3_backend_from_env"]
