"""Streaming-response helpers for node functions.

Split into a package grouped by streaming stage; the public class
``NodeStreamingResponseHelper`` is assembled from stage-specific
mixins:

- ``_base`` — entry point, max-token handling, pipeline max-tokens
- ``_stream_attempt`` — retry / fallback decision logic
- ``_stream_loop`` — chunk iteration and per-chunk processing
- ``_stream_message`` — final message construction, truncation checks
- ``_stream_usage`` — token-usage recording (per-tool split)
"""

from __future__ import annotations

# Redundant aliases mark intentional re-exports (names consumers
# import from the package — node_functions_mixin.py and the unit
# tests in test_distributed_limiter.py, test_truncation_detection.py,
# and test_inspection_model_visibility.py).
from airunner_services.llm.managers.mixins.node_streaming_response_helper._base import (
    NodeStreamingResponseHelperBase as NodeStreamingResponseHelperBase,
)
from airunner_services.llm.managers.mixins.node_streaming_response_helper._stream_attempt import (
    NodeStreamingAttemptMixin as NodeStreamingAttemptMixin,
)
from airunner_services.llm.managers.mixins.node_streaming_response_helper._stream_loop import (
    NodeStreamingLoopMixin as NodeStreamingLoopMixin,
)
from airunner_services.llm.managers.mixins.node_streaming_response_helper._stream_message import (
    NodeStreamingMessageMixin as NodeStreamingMessageMixin,
    _iteration_label as _iteration_label,
)
from airunner_services.llm.managers.mixins.node_streaming_response_helper._stream_usage import (
    NodeStreamingUsageMixin as NodeStreamingUsageMixin,
)


class NodeStreamingResponseHelper(
    NodeStreamingAttemptMixin,
    NodeStreamingLoopMixin,
    NodeStreamingMessageMixin,
    NodeStreamingUsageMixin,
    NodeStreamingResponseHelperBase,
):
    """Handle streamed chunk parsing for workflow nodes."""


__all__ = [
    "NodeStreamingResponseHelper",
    "_iteration_label",
]
