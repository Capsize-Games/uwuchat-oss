"""Complexity scorer for user messages.

Pure heuristics, no LLM call, no network, no dependencies beyond stdlib.
Returns a float in [0.0, 1.0] and maps to a named tier via the active
pipeline config.
"""

from __future__ import annotations

import math
import re
from typing import Tuple

# ── Signals ────────────────────────────────────────────────────────────────

_COMPLEXITY_QUESTION_WORDS: frozenset[str] = frozenset(
    {
        "why",
        "how",
        "explain",
        "compare",
        "analyze",
        "describe",
        "difference",
        "relationship",
        "effect",
        "cause",
        "mechanism",
        "implications",
    }
)

_CLAUSE_WORDS: frozenset[str] = frozenset(
    {
        "because",
        "although",
        "however",
        "unless",
        "whereas",
        "therefore",
        "consequently",
        "furthermore",
        "nevertheless",
    }
)

_TECHNICAL_VOCABULARY: frozenset[str] = frozenset(
    {
        # Science / physics
        "entropy",
        "quantum",
        "thermodynamic",
        "osmosis",
        "catalyst",
        "photosynthesis",
        "mitochondria",
        "genome",
        "neuron",
        "algorithm",
        "derivative",
        "integral",
        "velocity",
        "momentum",
        "electromagnetic",
        "relativity",
        "nuclear",
        "protein",
        "enzyme",
        "isotope",
        "molecule",
        "atomic",
        "fusion",
        "fission",
        "wavelength",
        "diffraction",
        "oxidation",
        "equilibrium",
        "turbulence",
        "viscosity",
        "resonance",
        "diffusion",
        "electrolysis",
        "polymer",
        "allele",
        "chromosome",
        "phenotype",
        "epigenetic",
        "synapse",
        "neurotransmitter",
        "hormone",
        "metabolite",
        "taxonomy",
        "ecosystem",
        "biodiversity",
        "tectonic",
        "stratosphere",
        "cryosphere",
        "paleoclimate",
        "geothermal",
        "subduction",
        "accretion",
        "cosmology",
        "singularity",
        "supernova",
        "exoplanet",
        "parallax",
        "redshift",
        "heliocentric",
        "gravitational",
        "inertia",
        "capacitance",
        "inductance",
        "semiconductor",
        "superconductivity",
        "ferromagnetism",
        "dielectric",
        "photon",
        "boson",
        "quark",
        "lepton",
        "neutrino",
        "antimatter",
        "superposition",
        "entanglement",
        "wavefunction",
        "eigenstate",
        "tunneling",
        "coherence",
        "decoherence",
        "interferometry",
        # Math
        "logarithm",
        "polynomial",
        "eigenvector",
        "probability",
        "hypothesis",
        "coefficient",
        "theorem",
        "matrix",
        "asymptote",
        "permutation",
        "combinatorics",
        "convergence",
        "differential",
        "exponent",
        "factorial",
        "manifold",
        "topology",
        "isomorphism",
        "orthogonal",
        "determinant",
        "stochastic",
        "extrapolation",
        "interpolation",
        "recursive",
        "fractal",
        "gaussian",
        "bayesian",
        "markov",
        "fourier",
        "laplacian",
        "eigenvalue",
        "tensor",
        "vectorization",
        "optimization",
        "gradient",
        # Medical
        "diagnosis",
        "pathology",
        "symptom",
        "prognosis",
        "etiology",
        "pharmacology",
        "metabolism",
        "inflammation",
        "antibody",
        "carcinoma",
        "neurological",
        "cardiovascular",
        "respiratory",
        "pharmaceutical",
        "immunology",
        "epidemiology",
        "oncology",
        "radiology",
        "anesthesia",
        "biopsy",
        "malignant",
        "benign",
        "metastasis",
        "remission",
        "autoimmune",
        "antigen",
        "lymphocyte",
        "cytokine",
        "ischemic",
        "thrombosis",
        "embolism",
        "sepsis",
        "fibrosis",
        "cirrhosis",
        "hypertension",
        "arrhythmia",
        "endoscopy",
        "laparoscopy",
        "histology",
        "karyotype",
        "genotype",
        "phenotype",
        "teratogenic",
        "iatrogenic",
        "nosocomial",
        "comorbidity",
        "contraindication",
        # Legal / formal
        "jurisdiction",
        "liability",
        "statute",
        "precedent",
        "indemnity",
        "arbitration",
        "regulation",
        "constitutional",
        "sovereignty",
        "plaintiff",
        "defendant",
        "amendment",
        "legislation",
        "tort",
        "estoppel",
        "subpoena",
        "injunction",
        "writ",
        "appeal",
        "acquittal",
        "extradition",
        "ratification",
        "nullification",
        "fiduciary",
        "eminent",
        "codification",
        "promulgation",
        "jurisprudence",
        "perjury",
        "affidavit",
        "deed",
        "easement",
        "lien",
        "encumbrance",
        "detrimental",
        "replevin",
        "usufruct",
        "prenuptial",
        "testator",
        "probate",
        "intestate",
        "domicile",
        # Programming / systems
        "recursion",
        "polymorphism",
        "concurrency",
        "asynchronous",
        "parallelism",
        "latency",
        "throughput",
        "refactor",
        "abstraction",
        "encapsulation",
        "inheritance",
        "serialization",
        "dependency",
        "middleware",
        "microservice",
        "immutable",
        "idempotent",
        "deterministic",
        "declarative",
        "imperative",
        "memoization",
        "monad",
        "functor",
        "closure",
        "currying",
        "protocol",
        "deserialize",
        "marshalling",
        "mutex",
        "semaphore",
        "deadlock",
        "race",
        "consensus",
        "sharding",
        "replication",
        "partitioning",
        "cap",
        "cryptography",
        "encryption",
        "hashing",
        "tokenization",
        "sandboxing",
        "containerization",
        "virtualization",
        "orchestration",
        "idempotency",
        "serializable",
        "normalization",
        "denormalization",
        "indexing",
        "btree",
        "bloom",
        "raft",
        "paxos",
        "gossip",
        "backpressure",
        "circuit",
        "bulkhead",
        "throttle",
    }
)

_CLAMP_MATH: float = 150.0
_AVG_WORD_OFFSET: float = 3.0
_AVG_WORD_DIVISOR: float = 6.0
_QUESTION_MAX: int = 3
_WEIGHT_LENGTH: float = 0.15
_WEIGHT_AVG_WORD: float = 0.15
_WEIGHT_QUESTION: float = 0.20
_WEIGHT_CLAUSE: float = 0.15
_WEIGHT_TECH: float = 0.25
_WEIGHT_STRUCT: float = 0.10


# ── Public API ──────────────────────────────────────────────────────────────


def score(text: str) -> float:
    """Return a complexity score in [0.0, 1.0] for the given user message.

    Never raises.  Empty / whitespace-only / None input returns 0.0.
    """
    try:
        if not text or not text.strip():
            return 0.0
        text = text.strip()
        words = _words(text)
        word_count = len(words)
        if word_count == 0:
            return 0.0
        return _clamp(
            _WEIGHT_LENGTH * _length_signal(word_count)
            + _WEIGHT_AVG_WORD * _avg_word_length_signal(words)
            + _WEIGHT_QUESTION * _question_complexity_signal(words)
            + _WEIGHT_CLAUSE * _clause_density_signal(text, words)
            + _WEIGHT_TECH * _technical_term_rate_signal(words)
            + _WEIGHT_STRUCT * _structural_complexity_signal(text, word_count)
        )
    except Exception:
        return 0.0


def classify(text: str) -> Tuple[float, str]:
    """Return (score, tier_name) using the active pipeline tier config.

    Walks the ``tiers`` list in the DIALOGUE pipeline key to find the
    first tier whose ``max_complexity >= score``.  Falls back to
    ``"standard"`` when ``tiers`` is absent or misconfigured.
    """
    s = score(text)
    tier_name = _resolve_tier(s)
    return s, tier_name


# ── Signal helpers ──────────────────────────────────────────────────────────


def _words(text: str) -> list[str]:
    """Return lowercased words from *text*, stripping punctuation."""
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp *value* to [*lo*, *hi*]."""
    return max(lo, min(hi, value))


def _length_signal(word_count: int) -> float:
    """log(word_count + 1) / log(150), capped at 1.0."""
    return _clamp(math.log(word_count + 1) / math.log(_CLAMP_MATH))


def _avg_word_length_signal(words: list[str]) -> float:
    """Mean char length of words; (mean - 3) / 6, clamped 0-1."""
    if not words:
        return 0.0
    mean = sum(len(w) for w in words) / len(words)
    return _clamp((mean - _AVG_WORD_OFFSET) / _AVG_WORD_DIVISOR)


def _question_complexity_signal(words: list[str]) -> float:
    """Count of complexity-question words / 3, capped at 1."""
    if not words:
        return 0.0
    hits = sum(1 for w in words if w in _COMPLEXITY_QUESTION_WORDS)
    return _clamp(hits / _QUESTION_MAX)


def _clause_density_signal(text: str, words: list[str]) -> float:
    """(comma + semicolon + clause_word) / max(word_count, 1)."""
    if not words:
        return 0.0
    punct = text.count(",") + text.count(";")
    clause_hits = sum(1 for w in words if w in _CLAUSE_WORDS)
    return _clamp((punct + clause_hits) / max(len(words), 1))


def _technical_term_rate_signal(words: list[str]) -> float:
    """Technical term hits / max(word_count, 1), capped at 1."""
    if not words:
        return 0.0
    hits = sum(1 for w in words if w in _TECHNICAL_VOCABULARY)
    return _clamp(hits / max(len(words), 1))


def _structural_complexity_signal(text: str, word_count: int) -> float:
    """(colon + paren + quote) / max(word_count, 1), capped at 1."""
    if word_count == 0:
        return 0.0
    punct = text.count(":") + text.count("(") + text.count(")")
    punct += text.count('"') + text.count("'")
    return _clamp(punct / word_count)


# ── Tier resolution ─────────────────────────────────────────────────────────


def _resolve_tier(score_val: float) -> str:
    """Find the first tier whose max_complexity >= *score_val*."""
    try:
        from airunner_services.llm.pipeline_loader import pipeline_config

        cfg = pipeline_config("DIALOGUE")
        tiers: list = cfg.get("tiers", [])
        if not tiers or not isinstance(tiers, list):
            return _default_tier()
        for tier in tiers:
            if not isinstance(tier, dict):
                continue
            max_c = tier.get("max_complexity")
            if max_c is None:
                continue
            if float(max_c) >= score_val:
                tier_name = tier.get("name")
                if tier_name and isinstance(tier_name, str):
                    return tier_name
        return _default_tier()
    except Exception:
        return "standard"


def _default_tier() -> str:
    """Return the fallback tier name when tiers are unconfigured."""
    try:
        from airunner_services.llm.pipeline_loader import pipeline_config

        cfg = pipeline_config("DIALOGUE")
        tiers: list = cfg.get("tiers", [])
        if tiers and isinstance(tiers, list):
            for tier in tiers:
                if isinstance(tier, dict) and tier.get("name"):
                    return tier["name"]
    except Exception:
        pass
    return "standard"


__all__ = ["score", "classify"]
