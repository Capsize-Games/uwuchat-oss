"""LLM action types used by service and GUI workflows."""

from enum import Enum


class LLMActionType(Enum):
    """LLM action types used by service and GUI workflows."""

    NONE = "None"
    CHAT = "RESPOND: Choose this action if you want to respond to the user."
    GENERATE_IMAGE = (
        "GENERATE IMAGE: Choose this action if you want to generate an "
        "image."
    )
    APPLICATION_COMMAND = "APPLICATION_COMMAND"
    UPDATE_MOOD = "UPDATE_MOOD"
    QUIT_APPLICATION = (
        "QUIT APPLICATION: If the users requests that you quit the "
        "application, choose this action."
    )
    TOGGLE_FULLSCREEN = (
        "TOGGLE FULLSCREEN: If the user requests to toggle fullscreen "
        "mode, choose this action."
    )
    TOGGLE_TTS = (
        "TOGGLE TEXT-TO-SPEECH: If the user requests that you turn on or "
        "off or toggle text-to-speech, choose this action."
    )
    PERFORM_RAG_SEARCH = (
        "SEARCH: If the user requests that you search for information, "
        "choose this action."
    )
    SUMMARIZE = "SUMMARIZE"
    DO_NOTHING = (
        "DO NOTHING: If the user's request is unclear or you are unable "
        "to determine the user's intent, choose this action."
    )
    GET_WEATHER = "get_weather"
    STORE_DATA = "store_data"
    SEARCH = "search"
    DECISION = "decision"
    CODE = "code"
    WORKFLOW = "workflow"
    FILE_INTERACTION = "file_interaction"
    WORKFLOW_INTERACTION = "workflow_interaction"
    DEEP_RESEARCH = "deep_research"
