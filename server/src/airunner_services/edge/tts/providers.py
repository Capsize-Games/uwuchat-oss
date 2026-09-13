"""Edge TTS provider configuration — local TTS engine metadata.

This module contains model file requirements, engine capabilities, and
download metadata for local TTS engines (eSpeak and OpenVoice/MeloTTS).
"""

from __future__ import annotations

from typing import Any, Dict, List

from airunner_services.contract_enums import TTSModel

# ------------------------------------------------------------------
# Supported engines
# ------------------------------------------------------------------

SUPPORTED_TTS_ENGINES: List[str] = [
    TTSModel.ESPEAK.value,
    TTSModel.OPENVOICE.value,
]

# ------------------------------------------------------------------
# eSpeak configuration
# ------------------------------------------------------------------

ESPEAK_VOICES: Dict[str, List[str]] = {
    "Male": ["m1", "m2", "m3"],
    "Female": ["f1", "f2", "f3"],
}

ESPEAK_RATE_RANGE = {"min": -100, "max": 100, "default": 0}
ESPEAK_PITCH_RANGE = {"min": -100, "max": 100, "default": 0}
ESPEAK_VOLUME_RANGE = {"min": 0, "max": 100, "default": 100}
ESPEAK_PUNCTUATION_MODES = ["none", "all", "some"]

ESPEAK_CONFIG: Dict[str, Any] = {
    "voices": ESPEAK_VOICES,
    "rate": ESPEAK_RATE_RANGE,
    "pitch": ESPEAK_PITCH_RANGE,
    "volume": ESPEAK_VOLUME_RANGE,
    "punctuation_modes": ESPEAK_PUNCTUATION_MODES,
}

# ------------------------------------------------------------------
# OpenVoice / MeloTTS model file requirements
# ------------------------------------------------------------------

OPENVOICE_BERT_MODELS: Dict[str, List[str]] = {
    "google-bert/bert-base-multilingual-uncased": [
        "config.json",
        "model.safetensors",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.txt",
    ],
    "google-bert/bert-base-uncased": [
        "config.json",
        "model.safetensors",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.txt",
    ],
    "dbmdz/bert-base-french-europeana-cased": [
        "config.json",
        "pytorch_model.bin",
        "tokenizer_config.json",
        "vocab.txt",
    ],
    "dccuchile/bert-base-spanish-wwm-uncased": [
        "config.json",
        "pytorch_model.bin",
        "tokenizer.json",
        "special_tokens_map.json",
        "tokenizer_config.json",
        "vocab.txt",
    ],
    "kykim/bert-kor-base": [
        "config.json",
        "pytorch_model.bin",
        "tokenizer_config.json",
        "vocab.txt",
    ],
    "tohoku-nlp/bert-base-japanese-v3": [
        "config.json",
        "pytorch_model.bin",
        "tokenizer_config.json",
        "vocab.txt",
    ],
    "hfl/chinese-roberta-wwm-ext-large": [
        "added_tokens.json",
        "config.json",
        "pytorch_model.bin",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.txt",
    ],
}

OPENVOICE_MELOTTS_MODELS: Dict[str, List[str]] = {
    "myshell-ai/MeloTTS-English": ["checkpoint.pth", "config.json"],
    "myshell-ai/MeloTTS-English-v3": ["checkpoint.pth", "config.json"],
    "myshell-ai/MeloTTS-French": ["checkpoint.pth", "config.json"],
    "myshell-ai/MeloTTS-Japanese": ["checkpoint.pth", "config.json"],
    "myshell-ai/MeloTTS-Spanish": ["checkpoint.pth", "config.json"],
    "myshell-ai/MeloTTS-Chinese": ["checkpoint.pth", "config.json"],
    "myshell-ai/MeloTTS-Korean": ["checkpoint.pth", "config.json"],
}

OPENVOICE_ALL_MODELS: Dict[str, List[str]] = {
    **OPENVOICE_BERT_MODELS,
    **OPENVOICE_MELOTTS_MODELS,
}

# ------------------------------------------------------------------
# Language support
# ------------------------------------------------------------------

OPENVOICE_LANGUAGES: Dict[str, Dict[str, Any]] = {
    "EN": {
        "name": "English",
        "melo_repo": "myshell-ai/MeloTTS-English",
        "bert_repo": "google-bert/bert-base-uncased",
    },
    "EN_V3": {
        "name": "English (v3)",
        "melo_repo": "myshell-ai/MeloTTS-English-v3",
        "bert_repo": "google-bert/bert-base-uncased",
    },
    "ES": {
        "name": "Spanish",
        "melo_repo": "myshell-ai/MeloTTS-Spanish",
        "bert_repo": "dccuchile/bert-base-spanish-wwm-uncased",
    },
    "FR": {
        "name": "French",
        "melo_repo": "myshell-ai/MeloTTS-French",
        "bert_repo": "dbmdz/bert-base-french-europeana-cased",
    },
    "ZH": {
        "name": "Chinese",
        "melo_repo": "myshell-ai/MeloTTS-Chinese",
        "bert_repo": "hfl/chinese-roberta-wwm-ext-large",
    },
    "JP": {
        "name": "Japanese",
        "melo_repo": "myshell-ai/MeloTTS-Japanese",
        "bert_repo": "tohoku-nlp/bert-base-japanese-v3",
    },
    "KR": {
        "name": "Korean",
        "melo_repo": "myshell-ai/MeloTTS-Korean",
        "bert_repo": "kykim/bert-kor-base",
    },
}


def get_espeak_config() -> Dict[str, Any]:
    """Return a copy of the eSpeak engine configuration."""
    return dict(ESPEAK_CONFIG)


def get_openvoice_files_for_languages(
    languages: List[str],
) -> Dict[str, List[str]]:
    """Return required model files for one or more languages."""
    result: Dict[str, List[str]] = {}
    for lang_code in languages:
        lang_info = OPENVOICE_LANGUAGES.get(lang_code, {})
        melo_repo = lang_info.get("melo_repo")
        bert_repo = lang_info.get("bert_repo")
        if melo_repo and melo_repo in OPENVOICE_ALL_MODELS:
            result[melo_repo] = OPENVOICE_ALL_MODELS[melo_repo]
        if bert_repo and bert_repo in OPENVOICE_ALL_MODELS:
            result[bert_repo] = OPENVOICE_ALL_MODELS[bert_repo]
    # Always include the multilingual BERT model.
    multilingual_repo = "google-bert/bert-base-multilingual-uncased"
    if multilingual_repo in OPENVOICE_ALL_MODELS:
        result[multilingual_repo] = OPENVOICE_ALL_MODELS[multilingual_repo]
    return result


def get_all_openvoice_files() -> Dict[str, List[str]]:
    """Return all OpenVoice/MeloTTS model file requirements."""
    return dict(OPENVOICE_ALL_MODELS)


def supported_language_codes() -> List[str]:
    """Return the list of supported OpenVoice language codes."""
    return list(OPENVOICE_LANGUAGES.keys())


def language_name(code: str) -> str:
    """Return the human-readable name for one OpenVoice language code."""
    info = OPENVOICE_LANGUAGES.get(code, {})
    return str(info.get("name", code))
