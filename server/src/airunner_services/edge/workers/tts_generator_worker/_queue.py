"""Worker-thread message queue handling."""

from __future__ import annotations

import re


class TTSGeneratorWorkerQueueMixin:
    """Queue control messages and sentence-buffer streaming text."""

    def on_add_to_queue_signal(self, data):
        self.add_to_queue(
            {
                "message": str(data.get("message", "")),
                "is_end_of_message": data.get("is_end_of_message", False)
                is True,
            }
        )

    @staticmethod
    def _is_control_queue_message(message) -> bool:
        """Return whether one queued payload must bypass interrupt drops."""
        if not isinstance(message, dict):
            return False
        message_type = message.get("_message_type")
        return isinstance(message_type, str) and bool(message_type.strip())

    def add_to_queue(self, message):
        if self.do_interrupt and not self._is_control_queue_message(message):
            return
        super().add_to_queue(message)

    def get_item_from_queue(self):
        message = super().get_item_from_queue()
        if message is None:
            return None
        if self.do_interrupt and not self._is_control_queue_message(message):
            return None
        return message

    def handle_message(self, data):
        message_type = data.get("_message_type") if data else None
        if message_type == "interrupt":
            self.on_interrupt_process_signal(data.get("data"))
            return
        if message_type == "unblock_tts_generator":
            self.on_unblock_tts_generator_signal(data.get("data"))
            return
        if message_type == "llm_text_streamed":
            self.on_llm_text_streamed_signal(data.get("data") or {})
            return
        if message_type == "llm_thinking":
            self.on_llm_thinking_signal(data.get("data") or {})
            return
        if message_type == "application_settings_changed":
            self.on_application_settings_changed_signal(data.get("data") or {})
            return
        if message_type == "tts_enable":
            self.on_enable_tts_signal(data.get("data"))
            return
        if message_type == "tts_disable":
            self.on_disable_tts_signal(data.get("data"))
            return

        if self.do_interrupt:
            return

        message = data.get("message", "")
        is_end_of_message = data.get("is_end_of_message", False)

        if isinstance(message, str):
            self.tokens.append(message)
        else:
            self.tokens.extend(message)

        text = "".join(self.tokens)
        timestamp_pattern = re.compile(r"\b(\d{1,2}):(\d{2})\b")
        text = timestamp_pattern.sub(r"\1 \2", text)

        def word_count(s):
            return len(s.split())

        word_threshold = self._sentence_generation_word_threshold()

        if is_end_of_message:
            if self._sentence_buffer or text.strip():
                all_text = " ".join(self._sentence_buffer)
                if text.strip():
                    all_text = (all_text + " " + text.strip()).strip()
                if all_text:
                    self._generate(all_text)
                    self.play_queue_started = True
            self._sentence_buffer = []
            self.tokens = []
        else:
            sentence_endings = [".", "?", "!", "\n"]
            for punctuation in sentence_endings:
                if self.do_interrupt:
                    return
                text = text.strip()
                if punctuation in text:
                    split_text = text.split(punctuation, 1)
                    if len(split_text) > 1:
                        before, after = split_text[0], split_text[1]
                        if word_count(before) >= 2:
                            sentence = before + punctuation
                            self._sentence_buffer.append(sentence)

                            total_words = sum(
                                word_count(sentence_text)
                                for sentence_text in self._sentence_buffer
                            )

                            should_generate = (
                                len(self._sentence_buffer)
                                >= self.SENTENCE_BUFFER_SIZE
                                or total_words >= word_threshold
                            )

                            if should_generate:
                                combined_text = " ".join(
                                    self._sentence_buffer
                                )
                                self._generate(combined_text)
                                self.play_queue_started = True
                                self._sentence_buffer = []

                            remaining_text = after.strip()
                            if not self.do_interrupt:
                                self.tokens = (
                                    [remaining_text]
                                    if remaining_text
                                    else []
                                )
                            break

        if self.do_interrupt:
            self.on_interrupt_process_signal()
