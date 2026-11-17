"""Log severity levels and how different spellings map onto them."""

# Higher number = more severe. UNKNOWN means "no level found in the line".
LEVEL_RANK = {
    "UNKNOWN": 0,
    "DEBUG": 1,
    "INFO": 2,
    "WARNING": 3,
    "ERROR": 4,
    "CRITICAL": 5,
}

# Entries at or above this rank are treated as problems and get grouped.
WARNING_RANK = LEVEL_RANK["WARNING"]
ERROR_RANK = LEVEL_RANK["ERROR"]

_ALIASES = {
    "TRACE": "DEBUG",
    "DEBU": "DEBUG",  # logrus (Go)
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "NOTICE": "INFO",
    "WARN": "WARNING",
    "WARNING": "WARNING",
    "ERR": "ERROR",
    "ERRO": "ERROR",  # logrus (Go)
    "ERROR": "ERROR",
    "SEVERE": "ERROR",  # java.util.logging
    "CRITICAL": "CRITICAL",
    "FATAL": "CRITICAL",
    "FATA": "CRITICAL",  # logrus (Go)
    "PANIC": "CRITICAL",
    "PANI": "CRITICAL",  # logrus (Go)
}


def normalize_level(word: str) -> str:
    """Map a level word like 'warn' or 'FATAL' to one of the LEVEL_RANK names."""
    return _ALIASES.get(word.upper(), "UNKNOWN")


def rank(level: str) -> int:
    return LEVEL_RANK.get(level, 0)
