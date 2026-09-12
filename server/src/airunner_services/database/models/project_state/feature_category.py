"""Category of feature for routing to specialized agents."""

from enum import Enum


class FeatureCategory(str, Enum):
    """Category of feature for routing to specialized agents."""

    FUNCTIONAL = "functional"
    UI = "ui"
    INTEGRATION = "integration"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    PERFORMANCE = "performance"
    SECURITY = "security"
