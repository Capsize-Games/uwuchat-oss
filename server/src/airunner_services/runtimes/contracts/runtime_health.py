"""Runtime health contract."""

from typing import Any, Dict

from pydantic import BaseModel, ConfigDict, Field

from airunner_services.runtimes.contracts.runtime_descriptor import (
    RuntimeDescriptor,
)
from airunner_services.runtimes.contracts.runtime_health_status import (
    RuntimeHealthStatus,
)


class RuntimeHealth(BaseModel):
    """Health payload shared by daemon and runtime clients."""

    model_config = ConfigDict(extra="forbid")

    descriptor: RuntimeDescriptor
    status: RuntimeHealthStatus = RuntimeHealthStatus.UNKNOWN
    details: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
