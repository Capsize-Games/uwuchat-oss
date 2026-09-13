"""Languages supported by OpenVoice and Melo runtimes."""

from enum import Enum


class AvailableLanguage(Enum):
    """Languages supported by OpenVoice and Melo runtimes."""

    AUTO = "Automatic"
    EN = "EN"
    ES = "ES"
    FR = "FR"
    ZH = "ZH"
    ZH_MIX_EN = "ZH_MIX_EN"
    JP = "JP"
    KR = "KR"
    SP = "SP"
