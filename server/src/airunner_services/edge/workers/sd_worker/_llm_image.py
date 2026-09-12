"""LLM-triggered image generation flow for SDWorker."""

from __future__ import annotations

from typing import Dict

from airunner_services.contract_enums import GeneratorSection
from airunner_services.contract_enums import LLMActionType
from airunner_services.database.models import ApplicationSettings
from airunner_services.utils.application.enum_resolver import (
    signal_code_proxy,
)

SignalCode = signal_code_proxy()


class SDWorkerLLMImageMixin:
    """Orchestrate image generation requested by the LLM tool."""

    def on_llm_image_prompt_generated(self, data: Dict) -> None:
        """Handle an image generation request triggered by the LLM tool.

        Orchestrates the full model-swap flow:
        1. Unload the LLM to free VRAM for the art model
        2. Update generator settings with the prompt and dimensions
        3. Trigger image generation with a post-generation callback
           that reloads the LLM and sends an acknowledgment.

        Args:
            data: Signal payload containing prompt, second_prompt,
                  image_type, width, and height in the 'message' key.
        """
        from airunner_services.data.tenant import (
            get_tenant_key,
            tenant_scope,
        )

        # Capture the tenant now (this handler runs in the LLM tool's tenant
        # context). The post-generation callback fires later, possibly on a
        # thread without that context, so it must re-apply this key — otherwise
        # the LLM reload + ack read model/conversation settings from
        # tenant_anonymous ("No model path configured").
        tenant_key = get_tenant_key()

        message = data.get("message", {})
        prompt = message.get("prompt", "")
        second_prompt = message.get("second_prompt", "")
        image_type = message.get("image_type", "txt2img")
        width = message.get("width", 1024)
        height = message.get("height", 768)

        # 1. Unload the LLM to free VRAM for the art model
        self.logger.info(
            "LLM-triggered image generation: prompt=%s, "
            "width=%s, height=%s",
            prompt[:80],
            width,
            height,
        )
        self.emit_signal(SignalCode.LLM_UNLOAD_SIGNAL, {})

        # 2. Update generator settings with the prompt data so
        #    _process_image_request picks them up when building
        #    the ImageRequest.
        self.update_generator_settings(
            prompt=prompt,
            second_prompt=second_prompt,
        )
        # NOTE: pass the ORM model class, not ``type(self.application_settings)``
        # — ``application_settings`` returns an ``ApplicationSettingsData``
        # dataclass, and ``_update_settings_model`` needs the mapped model
        # (it reads ``model_cls.__tablename__``), otherwise the persist raises
        # ``'ApplicationSettingsData' has no attribute '__tablename__'``.
        self._update_settings_model(
            ApplicationSettings,
            working_width=width,
            working_height=height,
        )

        # Resolve the section string to the GeneratorSection enum
        try:
            section = GeneratorSection(image_type)
        except ValueError:
            self.logger.warning(
                "Unknown image_type '%s', defaulting to TXT2IMG",
                image_type,
            )
            section = GeneratorSection.TXT2IMG

        # Store the pipeline_action so _process_image_request
        # can set the correct generator_section.
        self.update_generator_settings(
            pipeline_action=section.value,
        )

        # Ensure a model is selected (the LLM tool doesn't pick one), else the
        # diffusers manager aborts with "No model selected".
        self._ensure_art_model_selected()

        # 3. Register a post-generation callback that reloads the
        #    LLM and sends the acknowledgment to the chat agent.
        def _on_llm_image_complete(response: object) -> None:
            """Reload LLM and send acknowledgment after generation."""
            self.logger.info(
                "LLM-triggered image generation complete, " "reloading LLM..."
            )
            self._llm_image_callback = None

            # Re-apply the originating tenant so the reload + ack target the
            # caller's schema (this callback may run without tenant context).
            with tenant_scope(tenant_key):
                # Create a minimal LLMRequest for the acknowledgment
                from airunner_services.llm.llm_request import LLMRequest

                ack_request = LLMRequest.for_action(LLMActionType.CHAT)
                ack_request.do_tts_reply = True

                # Reload the LLM
                self.emit_signal(SignalCode.LLM_LOAD_SIGNAL, {})

                # Send acknowledgment via the proper request signal path
                import uuid

                request_id = str(uuid.uuid4())
                self.emit_signal(
                    SignalCode.LLM_TEXT_GENERATE_REQUEST_SIGNAL,
                    {
                        "llm_request": True,
                        "request_id": request_id,
                        "tenant_key": tenant_key,
                        "request_data": {
                            "action": LLMActionType.CHAT,
                            "prompt": (
                                "The image request has completed. "
                                "Write a single concise reply "
                                "(1 short sentence) acknowledging "
                                "the generated image."
                            ),
                            "command": None,
                            "llm_request": ack_request,
                            "do_tts_reply": True,
                            "request_id": request_id,
                        },
                    },
                )

        self._llm_image_callback = _on_llm_image_complete

        # 4. Trigger generation through the standard signal path.
        #    _process_image_request will apply the callback after
        #    creating the ImageRequest.
        self.on_do_generate_signal(message)
