"""Extension configuration for the UwU Creator."""

from airunner_services.extensions.config import ExtensionConfig


class UwuCreatorExtension(ExtensionConfig):
    name = "uwu_creator"
    label = "UwU Creator"
    description = (
        "Character creation wizard for UwUchat — personality types, "
        "species, worldview options, and pre-seeded character templates. "
        "Safe for outer-wall agents to edit."
    )
