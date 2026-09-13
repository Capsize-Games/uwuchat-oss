"""Document indexing request."""

from typing import List, Optional

from pydantic import BaseModel


class RagIndexRequest(BaseModel):
    """Document indexing request."""

    file_paths: Optional[List[str]] = None
