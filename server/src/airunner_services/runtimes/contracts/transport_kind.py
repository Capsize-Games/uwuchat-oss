"""Runtime transport enum."""

from enum import Enum


class TransportKind(str, Enum):
    """Transport used to reach a runtime."""

    IN_PROCESS = "in_process"
    UNIX_SOCKET = "unix_socket"
    HTTP = "http"
    WEBSOCKET = "websocket"
