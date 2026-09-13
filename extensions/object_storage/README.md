# Object Storage extension (S3)

Switches AI Runner from **local-filesystem** asset handling (dev) to
**object-storage + uploads** (prod). It implements the dev↔prod storage split:

| | Dev (extension OFF) | Prod (extension ON) |
|---|---|---|
| Documents/images source | Directory watchers register files found under `AIRUNNER_BASE_PATH` | Users **upload** via API |
| Watchers (documents, images, loras, models, embeddings) | Running | **Disabled** |
| Filesystem sync into DB | On (per-tenant, on panel load) | **Disabled** |
| Byte storage | Local filesystem | **S3** (or S3-compatible) |
| Object keys | local paths | `tenants/<schema>/{documents,images}/…` |

The per-tenant DB rows are unchanged — only *where the bytes live* and *how
records are created* differ.

## Enabling (production)

1. Add to `EXTENSIONS` (comma-separated env or config):

   ```
   EXTENSIONS=extensions.auth.config,extensions.fastsearch.config,extensions.conversation_inspector.config,extensions.object_storage.config
   ```

2. Configure S3 (credentials use the standard AWS chain — env, shared config,
   or instance/IRSA role; never hard-coded):

   ```
   AIRUNNER_S3_BUCKET=my-airunner-bucket
   AIRUNNER_S3_REGION=us-east-1
   AIRUNNER_S3_ENDPOINT_URL=          # optional: MinIO / R2 / other S3-compatible
   AIRUNNER_S3_PREFIX=                # optional: key prefix
   ```

3. Install `boto3` in the server image (only needed when this extension runs).

Enabling the extension alone disables the watchers and filesystem sync
(`ready()` → `set_filesystem_ingestion(False)`). If `AIRUNNER_S3_BUCKET` is
unset it logs a warning and falls back to the local backend.

## Endpoints (mounted at `/api/v1/object_storage`, auth required)

- `POST /documents` — multipart upload → stores bytes + registers a `Document`
  row in the caller's tenant. Returns `{id, name, path, …}`.
- `GET  /documents/{id}/content` — streams a stored document's bytes.
- `POST /images` — multipart upload → stores under the tenant's image prefix.
  Returns `{key, name, url}`.
- `GET  /images/content?key=…` — serves an image (redirects to a presigned URL
  on S3); enforces that the key belongs to the caller's tenant.

## Architecture

- Core seam: `airunner_services.storage` (`filesystem_ingestion_enabled()`,
  `set_filesystem_ingestion()`).
- Core backend abstraction: `airunner_services.storage.backends`
  (`StorageBackend`, `LocalStorageBackend`, `get/set_storage_backend`,
  `tenant_storage_key`).
- This extension provides `S3StorageBackend` and the upload/serve routes.
- The RAG document loader (`agent/document_loader.py`) materialises storage
  keys to a temp file, so uploaded/S3 documents remain indexable.

## Not yet wired (follow-up)

These still write/read the local filesystem and need migrating to
`get_storage_backend()` before a full S3 cutover:

- **Generated** image output (art pipeline `save_image`) and the image-serving
  routes (`api/routes/images.py`, currently `FileResponse`).
- The models/loras/embeddings *download* destinations (large binaries; likely
  stay on a mounted volume rather than S3).
