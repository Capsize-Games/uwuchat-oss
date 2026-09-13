"""Backward-compat shim — real code at airunner_services.edge.model_management.hardware_profiler."""

try:
    from airunner_services.edge.model_management.hardware_profiler import *
except ImportError:
    pass
