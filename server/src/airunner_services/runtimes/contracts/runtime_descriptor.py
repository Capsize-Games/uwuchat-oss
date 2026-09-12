"""Runtime descriptor contract."""

from typing import Optional

from pydantic import BaseModel, ConfigDict

from airunner_services.runtimes.contracts.runtime_kind import RuntimeKind
from airunner_services.runtimes.contracts.runtime_mode import RuntimeMode
from airunner_services.runtimes.contracts.transport_kind import TransportKind


class RuntimeDescriptor(BaseModel):
    """Descriptor used by the runtime registry and health checks."""

    model_config = ConfigDict(extra="forbid")

    runtime: RuntimeKind
    provider: str
    mode: RuntimeMode
    transport: TransportKind
    endpoint: Optional[str] = None
    supports_streaming: bool = False
    allows_model_control: bool = True
