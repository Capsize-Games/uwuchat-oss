"""Model scanner worker for discovering art models in the filesystem.

This worker scans the model directory structure to find and register AI models
for image generation (Z-Image, Stable Diffusion, etc.).

Directory structure expected:
    {base_path}/art/models/{version}/{pipeline_action}/{model_file_or_folder}

Example:
    ~/.local/share/airunner/art/models/Z-Image Turbo/txt2img/model.safetensors
    ~/.local/share/airunner/art/models/SDXL 1.0/txt2img/model.safetensors
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from airunner_services.contract_enums import ImageGenerator
from airunner_services.contract_enums import ArtVersion
from airunner_services.database.models.ai_models import AIModels
from airunner_services.database.session import session_scope
from airunner_services.workers.worker import Worker

# Mapping from version names to ImageGenerator categories
VERSION_TO_CATEGORY: dict[str, str] = {
    ArtVersion.Z_IMAGE_TURBO.value: ImageGenerator.ZIMAGE.value,
    ArtVersion.SDXL1_0.value: ImageGenerator.STABLEDIFFUSION.value,
    ArtVersion.SDXL_LIGHTNING.value: ImageGenerator.STABLEDIFFUSION.value,
    ArtVersion.SDXL_HYPER.value: ImageGenerator.STABLEDIFFUSION.value,
}

SUPPORTED_ZIMAGE_VERSIONS = {ArtVersion.Z_IMAGE_TURBO.value}

# Valid model file extensions
MODEL_EXTENSIONS = (".ckpt", ".safetensors", ".gguf")

# Folders that indicate a diffusers model directory
DIFFUSERS_REQUIRED_FOLDERS = (
    "scheduler",
    "text_encoder",
    "tokenizer",
    "unet",
    "vae",
)

# Folders to skip during scanning
SKIP_FOLDERS = ("controlnet_processors",)


def get_category_for_version(version: str) -> str:
    """Get the ImageGenerator category for a given version name.

    Args:
        version: The version folder name (e.g., 'Z-Image Turbo', 'SDXL 1.0')

    Returns:
        The category string (e.g., 'zimage', 'stablediffusion').
        Defaults to 'stablediffusion' for unknown versions.
    """
    return VERSION_TO_CATEGORY.get(
        version, ImageGenerator.STABLEDIFFUSION.value
    )


def is_supported_model_version(version: str) -> bool:
    """Return whether one scanned art version is still supported."""
    if version.startswith("Z-Image"):
        return version in SUPPORTED_ZIMAGE_VERSIONS
    return True


@dataclass
class ScannedModel:
    """Represents a model found during scanning."""

    name: str
    path: str
    version: str
    category: str
    pipeline_action: str


# ---------------------------------------------------------------------------
# Reusable scan/sync helpers (usable outside the worker thread).
#
# The startup worker scans with no tenant context, so models land in the
# anonymous schema and an authenticated user's schema stays empty ("No model
# selected").  These module-level helpers let an authenticated request sync
# the art models into the *current* tenant's schema on demand (see
# ``sync_art_models_into_current_tenant``), mirroring the KB folder-sync fix.
# ---------------------------------------------------------------------------
import logging as _logging

_logger = _logging.getLogger(__name__)


def _iter_directories(path: Path, should_continue=lambda: True):
    """Yield subdirectories of ``path``, skipping files."""
    try:
        for item in path.iterdir():
            if not should_continue():
                break
            if item.is_dir():
                yield item
    except PermissionError:
        _logger.warning("Permission denied accessing: %s", path)
    except OSError as exc:
        _logger.error("Error scanning %s: %s", path, exc)


def _identify_model_file(
    path: Path, version: str, category: str, action: str
) -> Optional[ScannedModel]:
    """Return a ScannedModel for a valid single-file model, else None."""
    if path.suffix.lower() not in MODEL_EXTENSIONS:
        return None
    return ScannedModel(
        name=path.stem,
        path=str(path),
        version=version,
        category=category,
        pipeline_action=action,
    )


def _identify_model_directory(
    path: Path, version: str, category: str, action: str
) -> Optional[ScannedModel]:
    """Return a ScannedModel for a valid diffusers directory, else None."""
    is_diffusers = all(
        (path / folder).exists() for folder in DIFFUSERS_REQUIRED_FOLDERS
    )
    if not is_diffusers:
        return None
    return ScannedModel(
        name=path.name,
        path=str(path),
        version=version,
        category=category,
        pipeline_action=action,
    )


def _identify_model(
    path: Path, version: str, action: str
) -> Optional[ScannedModel]:
    """Identify whether ``path`` is a valid model file or directory."""
    category = get_category_for_version(version)
    if path.is_file():
        return _identify_model_file(path, version, category, action)
    if path.is_dir():
        return _identify_model_directory(path, version, category, action)
    return None


def discover_art_models(
    base_path: Path, should_continue=lambda: True
) -> List[ScannedModel]:
    """Walk the art models tree and return discovered models (no DB writes)."""
    models: List[ScannedModel] = []
    if not base_path.exists():
        return models
    for version_dir in _iter_directories(base_path, should_continue):
        if not should_continue():
            break
        version_name = version_dir.name
        if not is_supported_model_version(version_name):
            _logger.debug("Skipping unsupported art version: %s", version_name)
            continue
        for action_dir in _iter_directories(version_dir, should_continue):
            if not should_continue():
                break
            action_name = action_dir.name
            if action_name in SKIP_FOLDERS:
                continue
            try:
                items = list(action_dir.iterdir())
            except OSError as exc:
                _logger.error("Error scanning %s: %s", action_dir, exc)
                continue
            for item in items:
                if not should_continue():
                    break
                model = _identify_model(item, version_name, action_name)
                if model:
                    models.append(model)
    return models


def build_ai_model(scanned: ScannedModel) -> AIModels:
    """Create an AIModels ORM instance from a ScannedModel."""
    model = AIModels()
    model.name = scanned.name
    model.path = scanned.path
    model.branch = "main"
    model.version = scanned.version
    model.category = scanned.category
    model.pipeline_action = scanned.pipeline_action
    model.enabled = True
    model.model_type = "art"
    model.is_default = False
    return model


def upsert_art_models(
    session, scanned: List[ScannedModel], should_continue=lambda: True
) -> None:
    """Upsert scanned models into ``aimodels`` using the given session."""
    for m in scanned:
        if not should_continue():
            break
        ai = build_ai_model(m)
        existing = (
            session.query(AIModels).filter(AIModels.path == ai.path).first()
        )
        if existing:
            existing.name = ai.name
            existing.branch = ai.branch
            existing.version = ai.version
            existing.category = ai.category
            existing.pipeline_action = ai.pipeline_action
            existing.enabled = True
            existing.model_type = ai.model_type
            existing.is_default = ai.is_default
        else:
            session.add(ai)


def sync_art_models_into_current_tenant(base_path: Path) -> int:
    """Scan ``base_path`` and upsert models into the current tenant schema.

    Uses the ambient ``session_scope()`` so the caller's tenant context
    determines the target schema.  Safe to call from an authenticated
    request to populate that user's art models on demand.  Returns the
    number of models found on disk.
    """
    scanned = discover_art_models(base_path)
    if not scanned:
        return 0
    with session_scope() as session:
        upsert_art_models(session, scanned)
    return len(scanned)


class ModelScannerWorker(Worker):
    """Worker that scans the filesystem for AI models.

    Scans the configured model directory for art models and registers them
    in the database. Handles both single-file models (.safetensors, .gguf, .ckpt)
    and diffusers-format model directories.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def handle_message(self, _message) -> None:
        """Process a scan request message."""
        if not self.running:
            return
        self.scan_for_models()
        if not self.running:
            return
        self.remove_missing_models()

    @property
    def model_base_path(self) -> Path:
        """Get the base path for art models."""
        return (
            Path(self.path_settings.base_path).expanduser() / "art" / "models"
        )

    def scan_for_models(self) -> None:
        """Scan the model directory and sync found models to the database.

        For each model found on disk, upsert (insert or update) into the
        ``aimodels`` table matched by path.  Models no longer on disk are
        removed separately by ``remove_missing_models``.
        """
        self.logger.debug("Starting model scan")
        model_path = self.model_base_path
        if not self.running:
            return
        if not model_path.exists():
            self.logger.debug(f"Creating model path: {model_path}")
            model_path.mkdir(parents=True, exist_ok=True)
        scanned = discover_art_models(model_path, lambda: self.running)
        if not self.running:
            return
        self.logger.debug("Found %d models on disk", len(scanned))
        if not scanned:
            return
        try:
            with session_scope() as session:
                upsert_art_models(session, scanned, lambda: self.running)
            self.logger.debug("Synced %d models to database", len(scanned))
        except Exception:
            self.logger.exception("Failed to sync scanned models to database")

    def remove_missing_models(self) -> None:
        """Remove database entries for models that no longer exist on disk."""
        existing_models = AIModels.objects.all()

        for model in existing_models:
            if not self.running:
                break
            if not Path(model.path).exists():
                self.logger.debug(
                    f"Removing missing model: {model.name} (id={model.id})"
                )
                AIModels.objects.delete(model.id)
