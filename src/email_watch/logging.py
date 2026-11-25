import enum
import sys

from typing import TextIO


def _log_primitive(stream: TextIO, text: str) -> None:
    stream.write(text)
    stream.flush()


def _log_with_prefix(stream: TextIO, prefix: str, msg: str) -> None:
    # In multi-line messages, the second and subsequent lines do not start
    # with the log-level prefix, so they are not recorded
    # under an unintended log level.
    #
    # Implementation note:
    # If msg is empty, msg[-1] will raise an IndexError. So use msg[-1:]
    # instead.
    text = msg[:-1].replace("\n", f"\n{prefix}") + msg[-1:]
    text = f"{prefix}{text}"

    _log_primitive(stream, text)


class _LogLevel(enum.IntEnum):
    ERROR = 0
    WARN = 1
    INFO = 2
    DEBUG = 3


class _LoggingType(enum.StrEnum):
    NORMAL = "normal-logging"
    SYSTEMD = "systemd-logging"


LOGGING_TYPE = _LoggingType.NORMAL

PREFIX_TABLE = {
    _LoggingType.NORMAL: {
        _LogLevel.ERROR: "[email-watch] Error: ",
        _LogLevel.WARN: "[email-watch] Warn: ",
        _LogLevel.INFO: "[email-watch] Info: ",
        _LogLevel.DEBUG: "[email-watch] Debug: ",
    },
    _LoggingType.SYSTEMD: {
        _LogLevel.ERROR: "<3>[email-watch]",
        _LogLevel.WARN: "<4>[email-watch]",
        _LogLevel.INFO: "<6>[email-watch]",
        _LogLevel.DEBUG: "<7>[email-watch]",
    },
}


def enable_systemd_logging() -> None:
    global LOGGING_TYPE
    LOGGING_TYPE = _LoggingType.SYSTEMD # pyright: ignore[reportConstantRedefinition]


DEBUG_LOG: bool = False
def enable_debug_log() -> None:
    global DEBUG_LOG
    DEBUG_LOG = True # pyright: ignore[reportConstantRedefinition]


def info(msg: str, end: str = "\n"):
    global LOGGING_TYPE
    prefix = PREFIX_TABLE[LOGGING_TYPE][_LogLevel.INFO]
    _log_with_prefix(sys.stderr, prefix, f"{msg}{end}")


def warn(msg: str, end:str = "\n"):
    global LOGGING_TYPE
    prefix = PREFIX_TABLE[LOGGING_TYPE][_LogLevel.WARN]
    _log_with_prefix(sys.stderr, prefix, f"{msg}{end}")


def error(msg: str, end: str = "\n"):
    global LOGGING_TYPE
    prefix = PREFIX_TABLE[LOGGING_TYPE][_LogLevel.ERROR]
    _log_with_prefix(sys.stderr, prefix, f"{msg}{end}")


def debug(msg: str, end: str = "\n"):
    global LOGGING_TYPE, DEBUG_LOG
    if not DEBUG_LOG:
        return
    prefix = PREFIX_TABLE[LOGGING_TYPE][_LogLevel.DEBUG]
    _log_with_prefix(sys.stderr, prefix, f"{msg}{end}")
