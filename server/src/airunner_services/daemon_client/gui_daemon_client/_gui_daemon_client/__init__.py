"""HTTP client used by AIRunner clients to launch or connect to the daemon.

Decomposed into focused modules:

- ``_connection`` — connection lifecycle, state, and health checks
- ``_stale_daemon`` — stale dev-daemon detection and recycling
- ``_transport`` — HTTP request plumbing and tenant header forwarding
- ``_runtime_endpoints`` — runtime control, TTS, and STT endpoints
- ``_art_endpoints`` — art generation and component endpoints
- ``_download_endpoints`` — download job endpoints
- ``_conversation_endpoints`` — LLM streaming and conversation endpoints
- ``_llm_payload`` — legacy LLM payload serialization

``GuiDaemonClient`` is the composed public class; all existing
importers keep working unchanged.
"""

from __future__ import annotations

from airunner_services.daemon_client.gui_daemon_client._gui_daemon_client._art_endpoints import (
    _ART_JOB_POLL_INTERVAL_SECONDS,
    GuiDaemonClientArtEndpointsMixin,
)
from airunner_services.daemon_client.gui_daemon_client._gui_daemon_client._connection import (
    StateCallback,
)
from airunner_services.daemon_client.gui_daemon_client._gui_daemon_client._connection import (
    GuiDaemonClientConnectionMixin,
)
from airunner_services.daemon_client.gui_daemon_client._gui_daemon_client._conversation_endpoints import (
    GuiDaemonClientConversationEndpointsMixin,
)
from airunner_services.daemon_client.gui_daemon_client._gui_daemon_client._download_endpoints import (
    GuiDaemonClientDownloadEndpointsMixin,
)
from airunner_services.daemon_client.gui_daemon_client._gui_daemon_client._llm_payload import (
    GuiDaemonClientLLMPayloadMixin,
)
from airunner_services.daemon_client.gui_daemon_client._gui_daemon_client._runtime_endpoints import (
    GuiDaemonClientRuntimeEndpointsMixin,
)
from airunner_services.daemon_client.gui_daemon_client._gui_daemon_client._stale_daemon import (
    GuiDaemonClientStaleDaemonMixin,
)
from airunner_services.daemon_client.gui_daemon_client._gui_daemon_client._transport import (
    GuiDaemonClientTransportMixin,
)


class GuiDaemonClient(
    GuiDaemonClientConnectionMixin,
    GuiDaemonClientStaleDaemonMixin,
    GuiDaemonClientTransportMixin,
    GuiDaemonClientRuntimeEndpointsMixin,
    GuiDaemonClientArtEndpointsMixin,
    GuiDaemonClientDownloadEndpointsMixin,
    GuiDaemonClientConversationEndpointsMixin,
    GuiDaemonClientLLMPayloadMixin,
):
    """Start, connect to, and communicate with the local daemon."""


__all__ = [
    "_ART_JOB_POLL_INTERVAL_SECONDS",
    "GuiDaemonClient",
    "GuiDaemonClientArtEndpointsMixin",
    "GuiDaemonClientConnectionMixin",
    "GuiDaemonClientConversationEndpointsMixin",
    "GuiDaemonClientDownloadEndpointsMixin",
    "GuiDaemonClientLLMPayloadMixin",
    "GuiDaemonClientRuntimeEndpointsMixin",
    "GuiDaemonClientStaleDaemonMixin",
    "GuiDaemonClientTransportMixin",
    "StateCallback",
]
