"""Object storage extension — production asset storage via S3.

Enabling this extension (add ``extensions.object_storage`` to the
``EXTENSIONS`` setting) flips the app from local-filesystem mode to
object-storage mode:

* Directory watchers (documents / models / images) are disabled.
* On-request filesystem sync that registers local files is disabled.
* The active storage backend becomes S3 (configured via ``AIRUNNER_S3_*``).
* Documents and images are created only through the extension's
  authenticated, tenant-scoped upload endpoints.

Leave it out of ``EXTENSIONS`` in development to keep watchers + local
filesystem behavior.
"""

from __future__ import annotations

import logging

from airunner_services.extensions.config import ExtensionConfig

logger = logging.getLogger(__name__)


class ObjectStorageExtension(ExtensionConfig):
    name = "object_storage"
    label = "Object Storage (S3)"
    description = (
        "Production asset storage: disables filesystem watchers and stores "
        "uploaded documents and images in S3, scoped per tenant."
    )

    def ready(self) -> None:
        """Switch the app to upload-only / object-storage mode."""
        from airunner_services.storage import set_filesystem_ingestion

        # Disable directory watchers + on-request filesystem sync.
        set_filesystem_ingestion(False)
        logger.info(
            "object_storage: filesystem ingestion disabled (upload-only mode)."
        )

        # Install the S3 backend if configured; otherwise leave the default
        # (local) backend in place and warn — the operator must set
        # AIRUNNER_S3_BUCKET for object storage to actually take effect.
        try:
            from airunner_services.storage.backends import set_storage_backend
            from extensions.object_storage.server.s3_backend import (
                build_s3_backend_from_env,
            )

            backend = build_s3_backend_from_env()
            if backend is not None:
                set_storage_backend(backend)
                logger.info("object_storage: S3 storage backend installed.")
            else:
                logger.warning(
                    "object_storage: AIRUNNER_S3_BUCKET not set — uploads will "
                    "use the local backend. Set AIRUNNER_S3_* for S3 storage."
                )
        except Exception:
            logger.exception("object_storage: failed to install S3 backend.")
