"""Edge Art provider configuration — image generation model metadata.

This module contains generator capabilities, model file requirements,
and download metadata for local image generation pipelines (SDXL,
Z-Image, Upscaler, Safety Checker, ControlNet).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from airunner_services.contract_enums import (
    ArtVersion,
    ImageGenerator,
    Scheduler,
)

# ------------------------------------------------------------------
# Image generator capabilities
# ------------------------------------------------------------------


@dataclass
class GeneratorCapabilities:
    """Feature flags and dimension constraints for one image generator."""

    supports_negative_prompt: bool = True
    supports_second_prompt: bool = True
    supports_second_negative_prompt: bool = True
    default_width: int = 1024
    default_height: int = 1024
    max_width: int = 2048
    max_height: int = 2048
    min_width: int = 64
    min_height: int = 64
    dimension_step: int = 64
    prompt_guidance: str = ""


GENERATOR_CAPABILITIES: Dict[str, GeneratorCapabilities] = {
    ImageGenerator.STABLEDIFFUSION.value: GeneratorCapabilities(
        supports_negative_prompt=True,
        supports_second_prompt=True,
        supports_second_negative_prompt=True,
        default_width=1024,
        default_height=1024,
        prompt_guidance=(
            "SDXL supports detailed prompts with negative prompts to "
            "exclude unwanted elements. Use second_prompt for "
            "background/atmosphere details."
        ),
    ),
    ImageGenerator.ZIMAGE.value: GeneratorCapabilities(
        supports_negative_prompt=False,
        supports_second_prompt=False,
        supports_second_negative_prompt=False,
        default_width=1024,
        default_height=1024,
        prompt_guidance=(
            "Z-Image uses a single detailed prompt. No negative or "
            "secondary prompts. Include all details in the main "
            "prompt. Supports English and Chinese text rendering."
        ),
    ),
}

# ------------------------------------------------------------------
# Model file requirements
# ------------------------------------------------------------------

# Maps (version, pipeline_action) → {relative_path: expected_bytes}
MODEL_FILE_REQUIREMENTS: Dict[str, Dict[str, Dict[str, int]]] = {
    "SDXL 1.0": {
        "txt2img": {
            "scheduler/scheduler_config.json": 479,
            "text_encoder/config.json": 565,
            "text_encoder_2/config.json": 575,
            "tokenizer/merges.txt": 524619,
            "tokenizer/special_tokens_map.json": 472,
            "tokenizer/tokenizer_config.json": 737,
            "tokenizer/vocab.json": 1059962,
            "tokenizer_2/merges.txt": 524619,
            "tokenizer_2/special_tokens_map.json": 460,
            "tokenizer_2/tokenizer_config.json": 725,
            "tokenizer_2/vocab.json": 1059962,
            "unet/config.json": 1680,
            "vae/config.json": 642,
            "model_index.json": 609,
        },
        "inpaint": {
            "scheduler/scheduler_config.json": 479,
            "text_encoder/config.json": 565,
            "text_encoder_2/config.json": 575,
            "tokenizer/merges.txt": 524619,
            "tokenizer/special_tokens_map.json": 472,
            "tokenizer/tokenizer_config.json": 737,
            "tokenizer/vocab.json": 1059962,
            "tokenizer_2/merges.txt": 524619,
            "tokenizer_2/special_tokens_map.json": 460,
            "tokenizer_2/tokenizer_config.json": 725,
            "tokenizer_2/vocab.json": 1059962,
            "unet/config.json": 1680,
            "vae/config.json": 642,
            "model_index.json": 609,
        },
        "controlnet": {
            "config.json": 0,
            "diffusion_pytorch_model.fp16.safetensors": 0,
        },
    },
    "Z-Image Turbo": {
        "txt2img": {
            "model_index.json": 467,
            "scheduler/scheduler_config.json": 173,
            "text_encoder/config.json": 726,
            "text_encoder/generation_config.json": 239,
            "text_encoder/model-00001-of-00003.safetensors": 3957900840,
            "text_encoder/model-00002-of-00003.safetensors": 3987450520,
            "text_encoder/model-00003-of-00003.safetensors": 99630640,
            "text_encoder/model.safetensors.index.json": 32819,
            "tokenizer/merges.txt": 1671853,
            "tokenizer/tokenizer.json": 11422654,
            "tokenizer/tokenizer_config.json": 9732,
            "tokenizer/vocab.json": 2776833,
            "transformer/config.json": 473,
            "vae/config.json": 805,
            "vae/diffusion_pytorch_model.safetensors": 167666902,
        },
    },
    "Upscaler": {
        "x4": {
            "low_res_scheduler/scheduler_config.json": 300,
            "scheduler/scheduler_config.json": 348,
            "text_encoder/config.json": 634,
            "text_encoder/model.fp16.safetensors": 680821096,
            "tokenizer/merges.txt": 524619,
            "tokenizer/special_tokens_map.json": 460,
            "tokenizer/tokenizer_config.json": 825,
            "tokenizer/vocab.json": 1059962,
            "unet/config.json": 982,
            "vae/config.json": 587,
            "model_index.json": 485,
            "x4-upscaler-ema.safetensors": 3531269371,
        },
    },
    "Safety Checker": {
        "safety_checker": {
            "config.json": 4549,
            "pytorch_model.bin": 1216067303,
            "preprocessor_config.json": 342,
        },
    },
}

# ------------------------------------------------------------------
# ControlNet models
# ------------------------------------------------------------------

CONTROLNET_MODELS: List[Dict[str, str]] = [
    {
        "display_name": "Canny",
        "name": "canny",
        "path": "diffusers/controlnet-canny-sdxl-1.0",
        "version": "SDXL 1.0",
        "pipeline_action": "controlnet",
        "size": "320200",
    },
    {
        "display_name": "Depth Midas",
        "name": "depth_midas",
        "path": "diffusers/controlnet-depth-sdxl-1.0",
        "version": "SDXL 1.0",
        "pipeline_action": "controlnet",
        "size": "320200",
    },
]

# ------------------------------------------------------------------
# Supported schedulers (per generator)
# ------------------------------------------------------------------

SDXL_SCHEDULERS: List[str] = [
    Scheduler.EULER_ANCESTRAL.value,
    Scheduler.EULER.value,
    Scheduler.LMS.value,
    Scheduler.HEUN.value,
    Scheduler.DPM.value,
    Scheduler.DPM2.value,
    Scheduler.DPM_PP_2M.value,
    Scheduler.DPM2_K.value,
    Scheduler.DPM2_A_K.value,
    Scheduler.DPM_PP_2M_K.value,
    Scheduler.DPM_PP_2M_SDE_K.value,
    Scheduler.DDIM.value,
    Scheduler.UNIPC.value,
    Scheduler.DDPM.value,
    Scheduler.DEIS.value,
    Scheduler.DPM_2M_SDE_K.value,
    Scheduler.PLMS.value,
]

ZIMAGE_SCHEDULERS: List[str] = [
    Scheduler.FLOW_MATCH_EULER.value,
    Scheduler.FLOW_MATCH_LCM.value,
]

DEFAULT_IMAGE_GENERATOR = ImageGenerator.ZIMAGE.value
DEFAULT_ART_VERSION = ArtVersion.Z_IMAGE_TURBO.value
DEFAULT_SCHEDULER = Scheduler.FLOW_MATCH_EULER.value

# ------------------------------------------------------------------
# Public helpers
# ------------------------------------------------------------------


def get_capabilities(generator_name: str) -> GeneratorCapabilities:
    """Return capabilities for one image generator."""
    return GENERATOR_CAPABILITIES.get(
        generator_name,
        GeneratorCapabilities(),
    )


def get_file_requirements(
    version: str,
    pipeline_action: str,
) -> Dict[str, int]:
    """Return required files for one model version and pipeline action."""
    version_files = MODEL_FILE_REQUIREMENTS.get(version, {})
    return dict(version_files.get(pipeline_action, {}))


def get_controlnet_models() -> List[Dict[str, str]]:
    """Return the list of available ControlNet models."""
    return list(CONTROLNET_MODELS)


def get_schedulers_for_generator(
    generator_name: str,
) -> List[str]:
    """Return available schedulers for one image generator."""
    if generator_name == ImageGenerator.ZIMAGE.value:
        return list(ZIMAGE_SCHEDULERS)
    return list(SDXL_SCHEDULERS)
