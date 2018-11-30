from enum import Enum
from typing import Optional


class Language(Enum):
    ENGLISH = "en"
    GERMAN = "de"


def get_lang(name: str) -> Optional[Language]:
    return Language(name)
