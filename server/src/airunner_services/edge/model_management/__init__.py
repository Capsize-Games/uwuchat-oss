"""Edge model management package — imports guarded for cloud compat."""

try:
    from airunner_services.edge.model_management.base_model_manager import (
        BaseModelManager,
    )
    from airunner_services.edge.model_management.hardware_profiler import (
        HardwareProfiler,
    )
    from airunner_services.edge.model_management.model_manager_interface import (
        ModelManagerInterface,
    )
    from airunner_services.edge.model_management.quantization_strategy import (
        QuantizationStrategy,
    )
    from airunner_services.edge.model_management.model_registry import (
        ModelRegistry,
    )
    from airunner_services.edge.model_management.memory_allocator import (
        MemoryAllocator,
    )
    from airunner_services.edge.model_management.model_resource_manager import (
        ModelResourceManager,
        ModelState,
    )
    from airunner_services.edge.model_management.canvas_memory_tracker import (
        CanvasMemoryTracker,
    )
    from airunner_services.edge.model_management.model_load_balancer import (
        ModelLoadBalancer,
    )
except ImportError:
    BaseModelManager = None
    HardwareProfiler = None
    ModelManagerInterface = None
    QuantizationStrategy = None
    ModelRegistry = None
    MemoryAllocator = None
    ModelResourceManager = None
    ModelState = None
    CanvasMemoryTracker = None
    ModelLoadBalancer = None

__all__ = [
    "BaseModelManager",
    "HardwareProfiler",
    "ModelManagerInterface",
    "QuantizationStrategy",
    "ModelRegistry",
    "MemoryAllocator",
    "ModelResourceManager",
    "ModelState",
    "CanvasMemoryTracker",
    "ModelLoadBalancer",
]
