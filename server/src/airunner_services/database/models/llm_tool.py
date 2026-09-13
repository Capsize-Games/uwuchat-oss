"""Service-owned model for LLM-generated custom tools."""

from sqlalchemy import Boolean, Column, Integer, String, Text

from airunner_services.database.base import BaseModel


class LLMTool(BaseModel):
    """Persist custom LLM tools created by the user or the agent."""

    __tablename__ = "llm_tool"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False, index=True)
    display_name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    code = Column(Text, nullable=False)
    enabled = Column(Boolean, default=True)
    created_by = Column(String, default="user")
    version = Column(Integer, default=1)
    safety_validated = Column(Boolean, default=False)
    usage_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)

    @property
    def success_rate(self) -> float:
        """Calculate the success rate of tool usage."""
        if self.usage_count == 0:
            return 0.0
        return (self.success_count / self.usage_count) * 100

    def increment_usage(
        self,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        """Increment usage statistics after one execution."""
        self.usage_count += 1
        if success:
            self.success_count += 1
        else:
            self.error_count += 1
            self.last_error = error
        self.save()

    def validate_code_safety(self) -> tuple[bool, str]:
        """AST-based safety validation on the stored tool code.

        Uses :func:`~airunner_services.llm.core.code_sandbox_ast.validate_code_safety_ast`
        to perform allowlist-based AST validation before the code
        ever reaches ``exec()``.  The old substring-match denylist is
        replaced by this — AST analysis is immune to string
        obfuscation, whitespace tricks, and comment-based smuggling.
        """
        from airunner_services.llm.core.code_sandbox_ast import (
            validate_code_safety_ast,
        )

        return validate_code_safety_ast(self.code)

    def __repr__(self) -> str:
        """Return a readable representation for debug output."""
        return (
            f"<LLMTool(name='{self.name}', enabled={self.enabled}, "
            f"version={self.version})>"
        )


__all__ = ["LLMTool"]
