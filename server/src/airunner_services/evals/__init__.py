"""Persona and memory eval suite for UwUchat roleplaying chatbots."""

from airunner_services.evals.base_eval import EvalBase
from airunner_services.evals.persona_fidelity_eval import PersonaFidelityEval
from airunner_services.evals.memory_coherence_eval import MemoryCoherenceEval

__all__ = [
    "EvalBase",
    "PersonaFidelityEval",
    "MemoryCoherenceEval",
]
