"""Service-owned download job coordination.

Package split of the former ``job_service.py`` module.  The public
``DownloadJobService`` name is assembled from mixins that group the
original single class by concern:

- ``_base`` — job lifecycle state and shared tracker helpers
- ``_starters`` — async job-start entry points
- ``_hf_runners`` — HuggingFace background job runners
- ``_civitai_runners`` — CivitAI/URL background job runners
- ``_nltk_runner`` — the NLTK corpus download runner
- ``_helpers`` — module-level download helpers
"""

from __future__ import annotations

from airunner_services.downloads.job_service._base import DownloadJobBase
from airunner_services.downloads.job_service._civitai_runners import (
    DownloadJobCivitaiRunnersMixin,
)
from airunner_services.downloads.job_service._hf_runners import (
    DownloadJobHfRunnersMixin,
)
from airunner_services.downloads.job_service._nltk_runner import (
    DownloadJobNltkRunnerMixin,
)
from airunner_services.downloads.job_service._starters import (
    DownloadJobStartersMixin,
)


class DownloadJobService(
    DownloadJobStartersMixin,
    DownloadJobHfRunnersMixin,
    DownloadJobCivitaiRunnersMixin,
    DownloadJobNltkRunnerMixin,
    DownloadJobBase,
):
    """Coordinate provider downloads behind one shared job lifecycle."""


__all__ = ["DownloadJobService"]
