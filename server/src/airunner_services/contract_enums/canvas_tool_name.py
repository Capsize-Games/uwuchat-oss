"""Available canvas tools."""

from enum import Enum


class CanvasToolName(Enum):
    """Available canvas tools."""

    ACTIVE_GRID_AREA = "active_grid_area"
    BRUSH = "brush"
    ERASER = "eraser"
    SELECTION = "selection"
    GRID = "grid"
    MOVE = "move"
    NONE = "none"
