"""Canonical build metadata for the service package surface."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from setuptools import find_packages

VERSION = "6.0.0"

README = (Path(__file__).resolve().parents[1] / "README.md").read_text(
    encoding="utf-8"
)

CORE_REQUIREMENTS = [
    "numpy>=2.2.5,<3.0",
    "packaging>=24.0",
    "pillow==12.3.0",
    "pydantic>=2.7,<3.0",
    # nltk: PYSEC-2026-3740 (pathsec bypass on model-artifact APIs) has no
    # patched release; floor at the latest 3.10.x so we ship the newest
    # code and document that NLTK downloaders must never be pointed at
    # user-controlled paths (accepted risk — see dependency-scan.yml).
    "nltk>=3.10.3",
    "alembic==1.13.2",
    "sqlalchemy==2.0.38",
    "psycopg[binary]>=3.2.0",
    "pgvector>=0.3.6",
    "etils[epath]==1.12.2",
    "jinja2==3.1.6",
    "pyyaml==6.0.2",
    "python-dotenv==1.2.2",
    "fastapi>=0.115.0,<1.0",
    "python-multipart>=0.0.27",
    "uvicorn[standard]==0.34.0",
    "psutil>=7.0.0",
    "watchdog>=6.0.0",
    "requests-cache==1.2.1",
    # Error monitoring (gracefully degrades when SENTRY_DSN unset).
    "sentry-sdk[fastapi]>=2.0.0",
    # Password strength (zxcvbn entropy estimation).
    "zxcvbn>=4.4.28",
    # Web Push notifications (gracefully degrades when VAPID unset).
    "pywebpush>=2.0.0",
    # XML security — imported directly by kiwix_api + arxiv_provider.
    "defusedxml>=0.7.1",
    # Security floors for transitive-only dependencies (not imported
    # directly, but pinned so the resolver never lands on a known-CVE
    # version regardless of which package pulls it in).
    "requests>=2.33.0",
    "click>=8.3.3",
    # tornado: GHSA-8423-8fgw-73vq / CVE-2026-82397 / GHSA-wwv5-g3v4-889x
    # (multipart/urlencoded DoS + cookie-attr injection) fixed in 6.5.8.
    # Tornado is transitive via the jupyterlab stack; floor it so the
    # resolver cannot regress below the fix (dependency-security audit
    # 2026-09-06).
    "tornado>=6.5.8",
    # diskcache: PYSEC-2026-2447 has no fix release yet; pin exact
    # version so we know what we're shipping.
    "diskcache==5.6.3",
]

CELERY_REQUIREMENTS = [
    "celery[redis]>=5.4.0,<6.0",
    "redis>=5.0.0,<6.0",
]

ML_RUNTIME_REQUIREMENTS = [
    "torch>=2.10.0",
    "torchvision>=0.20.0",
    "torchaudio>=2.10.0",
    "accelerate==1.7.0",
    "huggingface-hub>=0.34.0,<2.0",
    "tokenizers==0.22.2",
    "optimum==1.25.1",
]

NVIDIA_REQUIREMENTS = [
    "nvidia-cuda-runtime",
    "nvidia-ml-py>=13.610.43",
]

HUGGINGFACE_REQUIREMENTS = [
    "diffusers>=0.30.0,<0.39.0",
    "controlnet_aux==0.0.10",
    "safetensors>=0.6.2",
    "kornia",
    "timm",
    "compel>=2.1.0",
    # transformers is capped at <5.0.0 because 5.x requires
    # huggingface-hub>=1.0 which introduces breaking API changes
    # across the langchain-huggingface / sentence_transformers
    # dependency chain.  See commit 4faddd4c7 for the full
    # compatibility analysis.  This leaves 4 known CVEs unresolved
    # (PYSEC-2025-217, PYSEC-2026-2288/2289/2290) — those are
    # accepted risk documented in .github/workflows/dependency-scan.yml.
    "transformers>=4.41.0,<5.0.0",
    # datasets: PYSEC-2026-3716 (folder-builder path traversal) fixed in
    # 5.0.1. Bumped from 4.0.0 (dependency-security audit 2026-09-06).
    "datasets==5.0.1",
    # jupyterlab is pulled in transitively by compel → notebook.
    # Pin >=4.6.2 to close 5 GitHub Security Advisories
    # (GHSA-h5v5-8746-g7mm, GHSA-whvh-wf3x-g77j, GHSA-gx64-gj6p-pc4c,
    #  GHSA-pppj-hq3g-57pj, GHSA-89vp-jrxv-24w8).  compel does not
    # actually use jupyterlab at runtime; this pin is a defense-in-
    # depth measure to keep a known-vulnerable version out of the
    # production image while compel's upstream dependency tree is
    # still declared this way.
    "jupyterlab>=4.6.2",
]

ART_REQUIREMENTS = [
    "DeepCache==0.1.1",
    "tomesd==0.1.3",
    "gguf==0.17.1",
]

LLM_NATIVE_REQUIREMENTS = [
    "llama-cpp-python==0.3.26",
    "bitsandbytes==0.49.2",
    "sentence_transformers==3.4.1",
    "cryptography==48.0.1",
    "tenseal>=0.3.14",
    "sumy==0.11.0",
    "sentencepiece==0.2.1",
    "lingua-language-detector==2.1.0",
    "markdown==3.8.1",
    "libzim==3.7.0",
    "mistral_common>=1.8.5",
    "rank-bm25>=0.2.2",
    "llama-cloud==0.1.23",
    "langchain-core==1.3.3",
    "langchain-huggingface>=1.2.0",
    "langgraph==1.0.10",
    "langsmith>=0.8.0",
    "langchain-ollama==1.0.0",
    "langchain-openai>=0.4.0",
    "langchain-text-splitters==1.1.2",
    "EbookLib==0.19",
    "mobi==0.4.1",
    "pypdf>=5.6.0",
    "presidio-analyzer>=2.2.0",
    # >=2.2.364 required: earlier releases cap cryptography<47.0.0,
    # which conflicts with the cryptography>=48.0.1 security floor.
    "presidio-anonymizer>=2.2.364",
    "spacy>=3.7.0",
]

# LLM safety — ONNX-based content scanning (prompt injection, toxicity,
# banned topics). NOT part of LLM_NATIVE_REQUIREMENTS / the default
# "server" extra: llm-guard 0.3.10 (the latest release on PyPI) hard-
# pins sentencepiece==0.2.0, which conflicts with this project's own
# sentencepiece==0.2.1 pin above -- installing it by default makes the
# entire "server" extra unresolvable. The module that imports it
# (llm/safety/_llm_guard_scanners.py) already lazy-imports and catches
# ImportError, so this being absent by default is the intended,
# supported state, not a bug -- operators who want prompt-injection/
# toxicity scanning can opt in via `pip install -e "./server[llm-guard]"`
# and accept the sentencepiece==0.2.0 downgrade themselves.
LLM_GUARD_REQUIREMENTS = ["llm-guard>=0.3.10"]

STT_NATIVE_REQUIREMENTS = ["sounddevice==0.5.1", "faster-whisper==1.2.1"]

LLM_WEATHER_REQUIREMENTS = [
    "requests-cache==1.2.1",
    "retry-requests==2.0.0",
]

TTS_REQUIREMENTS = [
    "inflect==7.5.0",
    "pycountry==24.6.1",
    "librosa==0.11.0",
    "torchcodec>=0.8.0",
]

OPENVOICE_REQUIREMENTS = [
    "librosa==0.11.0",
    "pydub==0.25.1",
    "wavmark==0.0.3",
    "eng_to_ipa==0.0.2",
    "inflect==7.5.0",
    "unidecode==1.4.0",
    "langid==1.1.6",
]

MELOTTS_REQUIREMENTS = [
    "txtsplit==1.0.0",
    "num2words==0.5.14",
    "g2p_en==2.1.0",
    "anyascii==0.3.2",
    "loguru==0.7.3",
]

OPENVOICE_CN_REQUIREMENTS = [
    "pypinyin==0.54.0",
    "jieba==0.42.1",
    "cn2an==0.5.23",
]

OPENVOICE_JP_REQUIREMENTS = [
    "unidic_lite==1.0.8",
    "unidic==1.1.0",
    "mecab-python3==1.0.10",
    "fugashi==1.4.0",
    "pykakasi==2.3.0",
]

OPENVOICE_KR_REQUIREMENTS = [
    "jamo==0.4.1",
    "python-mecab-ko==1.3.7",
    "python-mecab-ko-dic==2.1.1.post2",
]

OPENVOICE_TW_REQUIREMENTS = ["g2pkk>=0.1.2"]

GRUUT_SUPPORT_REQUIREMENTS = [
    "gruut[de,es,fr]==2.4.0",
    "networkx==3.4.2",
]

SEARCH_REQUIREMENTS = [
    "ddgs>=9.0.0",
    "aiohttp>=3.14.1",
    "google-api-python-client>=2.170.0",
    "wikipedia>=1.4.0",
    "scrapy>=2.16.0,<3.0",
]

COMPUTER_USE_REQUIREMENTS = [
    "pyautogui>=0.9.54",
    "pyscreeze>=1.0.1",
    "python-xlib>=0.33;platform_system=='Linux'",
    "pygetwindow>=0.0.9",
]

SYSTEM_DEP_EXTRAS = {"openvoice_jp", "openvoice_kr"}

DEVELOPMENT_REQUIREMENTS = [
    "pytest",
    "pytest-timeout",
    "pytest-asyncio>=0.24.0",
    "responses>=0.25.0",
    "coverage==7.8.0",
    "black==26.3.1",
    "ruff>=0.12.0",
    "pyinstaller==6.12.0",
    "flake8==7.2.0",
    "mypy==1.16.0",
    "autoflake==2.3.1",
    "pandas>=2.0.0",
    "pyarrow>=14.0.0",
    "tqdm>=4.0.0",
]

SERVICE_CONSOLE_SCRIPTS = [
    "airunner-daemon=airunner_services.daemon:main",
    "airunner-server=airunner_services.bin.airunner_server:main",
    "airunner-service=airunner_services.bin.airunner_service:main",
    "airunner-generate-migration="
    "airunner_services.bin.generate_migration:main",
    "airunner-hf-download=airunner_services.bin.airunner_hf_download:main",
    "airunner-civitai-download="
    "airunner_services.bin.airunner_civitai_download:main",
]


def unique_requirements(*groups: list[str]) -> list[str]:
    """Return one stable dependency list with duplicates removed."""
    dependencies: list[str] = []
    for group in groups:
        dependencies.extend(group)
    return list(dict.fromkeys(dependencies))


def _base_extras_require() -> dict[str, list[str]]:
    """Return the non-aggregate service extras."""
    return {
        "core": [],
        "nvidia": NVIDIA_REQUIREMENTS,
        "linux": [],
        "development": DEVELOPMENT_REQUIREMENTS,
        "dev": DEVELOPMENT_REQUIREMENTS,
        "art": ART_REQUIREMENTS,
        "huggingface": HUGGINGFACE_REQUIREMENTS,
        "llm-guard": LLM_GUARD_REQUIREMENTS,
        "llm-native": unique_requirements(
            ML_RUNTIME_REQUIREMENTS,
            LLM_NATIVE_REQUIREMENTS,
        ),
        "stt-native": STT_NATIVE_REQUIREMENTS,
        "art-python": unique_requirements(
            ML_RUNTIME_REQUIREMENTS,
            HUGGINGFACE_REQUIREMENTS,
            ART_REQUIREMENTS,
        ),
        "llm": unique_requirements(
            ML_RUNTIME_REQUIREMENTS,
            LLM_NATIVE_REQUIREMENTS,
            STT_NATIVE_REQUIREMENTS,
            ["pyttsx3==2.91"],
        ),
        "llm_weather": LLM_WEATHER_REQUIREMENTS,
        "llm-weather": LLM_WEATHER_REQUIREMENTS,
        "tts": TTS_REQUIREMENTS,
        "tts-python": unique_requirements(
            ML_RUNTIME_REQUIREMENTS,
            TTS_REQUIREMENTS,
            ["pyttsx3==2.91"],
            OPENVOICE_REQUIREMENTS,
            MELOTTS_REQUIREMENTS,
            OPENVOICE_CN_REQUIREMENTS,
            OPENVOICE_TW_REQUIREMENTS,
            GRUUT_SUPPORT_REQUIREMENTS,
        ),
        "openvoice": OPENVOICE_REQUIREMENTS,
        "melotts": MELOTTS_REQUIREMENTS,
        "openvoice_cn": OPENVOICE_CN_REQUIREMENTS,
        "openvoice_jp": OPENVOICE_JP_REQUIREMENTS,
        "openvoice_kr": OPENVOICE_KR_REQUIREMENTS,
        "openvoice_tw": OPENVOICE_TW_REQUIREMENTS,
        "gruut_support": GRUUT_SUPPORT_REQUIREMENTS,
        "search": SEARCH_REQUIREMENTS,
        "computer_use": COMPUTER_USE_REQUIREMENTS,
        "computer-use": COMPUTER_USE_REQUIREMENTS,
        # Heavy subset of server extras for the base image layer.
        # These are the disk-space-dominant packages — keeping them
        # pre-installed avoids re-downloading ~4 GB of wheels on every
        # build while keeping the GHCR base image small enough to fit
        # on a standard GitHub Actions runner (14 GB free).
        "server-deps": unique_requirements(
            ML_RUNTIME_REQUIREMENTS,
            HUGGINGFACE_REQUIREMENTS,
            [
                "sentence_transformers",
                "faster-whisper",
                "bitsandbytes",
            ],
        ),
        "edge": unique_requirements(
            ML_RUNTIME_REQUIREMENTS,
            NVIDIA_REQUIREMENTS,
            HUGGINGFACE_REQUIREMENTS,
            ART_REQUIREMENTS,
            LLM_NATIVE_REQUIREMENTS,
            STT_NATIVE_REQUIREMENTS,
            TTS_REQUIREMENTS,
            OPENVOICE_REQUIREMENTS,
            MELOTTS_REQUIREMENTS,
        ),
        "celery": CELERY_REQUIREMENTS,
        "cloud": unique_requirements(
            CELERY_REQUIREMENTS,
            [
                "langchain-core==1.3.3",
                "langchain-ollama==1.0.0",
                "langchain-openai>=0.4.0",
                "langgraph==1.0.10",
                "langsmith>=0.8.0",
                "langchain-text-splitters==1.1.2",
                # sentence_transformers provides local embedding for
                # pgvector RAG (HuggingFaceEmbeddings).  It pulls in
                # torch + transformers + huggingface-hub transitively,
                # which are the only heavy ML packages the cloud path
                # actually needs at runtime.
                "sentence_transformers",
                # langchain-huggingface wraps HuggingFaceEmbeddings
                # for the langchain retrieval pipeline.
                "langchain-huggingface>=0.1.0",
            ],
        ),
        "shared": [],  # shared extras are already in install_requires
    }


def _aggregate_extra(
    extras_require: dict[str, list[str]],
    *extra_names: str,
) -> list[str]:
    """Return one flattened aggregate extra dependency list."""
    dependencies: list[str] = []
    for extra_name in extra_names:
        dependencies.extend(extras_require[extra_name])
    return list(dict.fromkeys(dependencies))


def _aggregate_extras_require(
    extras_require: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Return the aggregate service extras."""
    server_extras = _aggregate_extra(
        extras_require,
        "celery",
        "llm-native",
        "stt-native",
        "art-python",
        "tts-python",
        "llm_weather",
    )
    aggregate_require = {**extras_require, "server": server_extras}
    desktop = _aggregate_extra(
        aggregate_require,
        "server",
        "llm_weather",
        "search",
        "computer_use",
        "nvidia",
        "linux",
    )
    aggregate_require["desktop"] = desktop
    all_native = _aggregate_extra(
        aggregate_require,
        "desktop",
        *sorted(SYSTEM_DEP_EXTRAS),
    )
    return {
        "server": server_extras,
        "desktop": desktop,
        "all": desktop,
        "all_dev": _aggregate_extra(
            {**aggregate_require, "all": desktop},
            "all",
            "development",
        ),
        "all_native": all_native,
        "all_dev_native": _aggregate_extra(
            {**aggregate_require, "all_native": all_native},
            "all_native",
            "development",
        ),
        "windows": _aggregate_extra(
            aggregate_require,
            "server",
            "llm_weather",
            "search",
            "computer_use",
            "nvidia",
        ),
    }


def build_extras_require() -> dict[str, list[str]]:
    """Return the extras map for the service package surface."""
    extras_require = _base_extras_require()
    extras_require.update(_aggregate_extras_require(extras_require))
    return extras_require


def build_setup_kwargs(*, package_source_dir: str) -> dict[str, Any]:
    """Return the setuptools metadata for the service package surface."""
    install_requires = [
        *CORE_REQUIREMENTS,
    ]
    return {
        "name": "airunner-services",
        "version": VERSION,
        "author": "Capsize LLC",
        "description": "AIRunner service package",
        "long_description": README,
        "long_description_content_type": "text/markdown",
        "license": "MIT",
        "author_email": "contact@uwuchat.com",
        "url": "https://github.com/Capsize-Games/airunner",
        "package_dir": {"": package_source_dir},
        "packages": find_packages(package_source_dir),
        "python_requires": ">=3.13.3",
        "install_requires": install_requires,
        "extras_require": build_extras_require(),
        "package_data": {
            "airunner_services": [
                "assets/reference_speakers/*.wav",
            ],
            "airunner_services.bin": ["*.sh"],
            "airunner_services.database": [
                "alembic.ini",
                "alembic/*.py",
                "alembic/*.mako",
                "alembic/versions/*.py",
            ],
        },
        "include_package_data": True,
        "entry_points": {"console_scripts": SERVICE_CONSOLE_SCRIPTS},
    }


__all__ = ["SERVICE_CONSOLE_SCRIPTS", "VERSION", "build_setup_kwargs"]
