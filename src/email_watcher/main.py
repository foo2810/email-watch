from __future__ import annotations

import argparse
import base64
import email
import email.message
import email.policy
import enum
import sys
import traceback
from imaplib import IMAP4, IMAP4_SSL
from pathlib import Path
from typing import TextIO


##### Logging #####

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
        _LogLevel.ERROR: "Error: ",
        _LogLevel.WARN: "Warn: ",
        _LogLevel.INFO: "Info: ",
        _LogLevel.DEBUG: "Debug: ",
    },
    _LoggingType.SYSTEMD: {
        _LogLevel.ERROR: "<3>",
        _LogLevel.WARN: "<4>",
        _LogLevel.INFO: "<6>",
        _LogLevel.DEBUG: "<7>",
    },
}

def enable_systemd_logging() -> None:
    global LOGGING_TYPE
    LOGGING_TYPE = _LoggingType.SYSTEMD

def info(msg: str, end: str = "\n"):
    global LOGGING_TYPE
    prefix = PREFIX_TABLE[LOGGING_TYPE][_LogLevel.INFO]
    _log_with_prefix(sys.stderr, prefix, f"{msg}{end}")

def debug(msg: str, end: str = "\n"):
    global LOGGING_TYPE
    prefix = PREFIX_TABLE[LOGGING_TYPE][_LogLevel.DEBUG]
    _log_with_prefix(sys.stderr, prefix, f"{msg}{end}")

def warn(msg: str, end:str = "\n"):
    global LOGGING_TYPE
    prefix = PREFIX_TABLE[LOGGING_TYPE][_LogLevel.WARN]
    _log_with_prefix(sys.stderr, prefix, f"{msg}{end}")

def error(msg: str, end: str = "\n"):
    global LOGGING_TYPE
    prefix = PREFIX_TABLE[LOGGING_TYPE][_LogLevel.ERROR]
    _log_with_prefix(sys.stderr, prefix, f"{msg}{end}")


##### IMAP helper #####

def encode_with_modified_utf7(s: str) -> str:
    utf16_be_encoded = s.encode("utf-16-be")
    mod_utf7_encoded = base64.b64encode(utf16_be_encoded) \
        .decode("ascii") \
        .replace("=", "") \
        .replace("/", ",")
    return f"&{mod_utf7_encoded}-"

def decode_with_modified_utf7(s: str) -> str:
    if len(s) < 3 or s[0] != "&" or s[-1] != "-":
        raise ValueError("encoded data is invalid")

    s_trim = s[1:-1]
    len_s_trim = len(s_trim)
    # Append padding to the string so that length is a multiple of 4
    if len_s_trim % 4 != 0:
        s_trim += "=" * (4 - len_s_trim%4)
    mod_b64_encoded = s_trim \
        .replace(",", "/") \
        .encode("ascii")
    utf16_be_encoded = base64.b64decode(mod_b64_encoded)
    decoded = utf16_be_encoded.decode("utf-16-be")
    return decoded

def imap_encode(s: str) -> str:
    encoded_str = ""
    part = ""
    for c in s:
        if 0x20 <= ord(c) <= 0x7e:
            encoded_part = ""
            if len(part) != 0:
                encoded_part = encode_with_modified_utf7(part)

            if c == "&":
                c = "&-"

            encoded_str += f"{encoded_part}{c}"
            part = ""
        else:
            part += c

    if len(part) != 0:
        encoded_str += encode_with_modified_utf7(part)
        part = ""

    return encoded_str

def imap_decode(encoded_str: str) -> str:
    decoded_str = ""

    idx = 0
    while idx < len(encoded_str):
        c = encoded_str[idx]
        if c == "&":
            idx_hyphen = encoded_str.find("-", idx)
            if idx_hyphen == idx+1:
                # "&-" -> "&"
                decode_part = "&"
            else:
                # "&<encoded>-" -> "<decoded>"
                decode_part = decode_with_modified_utf7(
                    encoded_str[idx:idx_hyphen+1]
                )
            decoded_str += decode_part
            idx = idx_hyphen + 1
        else:
            decoded_str += c
            idx += 1

    return decoded_str

def fetchall_email_uid(imap_handler: IMAP4, mailbox: str) -> list[int] | None:
    imap_handler.select(mailbox)

    try:
        status, data = imap_handler.fetch("1:*", "UID")
    except IMAP4.error as e:
        error(f"fetchall_email_uid: `FETCH 1:* UID` failed: {e}")
        status = "BAD"

    debug(f"fetchall_email_uid: FETCH status: {status}")

    if status != "OK":
        return None

    # "(<UID>)" --> <UID>
    def converter(ent: bytes) -> int:
        return int(ent.decode()[1:-1].split()[-1])

    uids = list(map(
        converter, filter(lambda ent: ent is not None, data)
    ))

    return uids

def fetch_emails_by_uids(
    imap_handler: IMAP4,
    uids: list[int]
) -> list[email.message.EmailMessage] | None:
    if not uids:
        return []

    uid_strs = list(map(str, uids))

    try:
        # Use "BODY.PEEK" not to set SEEN flag to the fetched emails
        status, fetched_data = imap_handler.uid(
            "FETCH", ",".join(uid_strs), "(BODY.PEEK[])"
        )
    except IMAP4.error as e:
        error(f"fetch_emails_by_uids: FETCH command failed: {e}")
        status = "BAD"

    debug(f"fetch_emails_by_uids: FETCH status: {status}")

    if status != "OK":
        return None

    emails = []
    for part_data in fetched_data:
        if not isinstance(part_data, tuple):
            continue

        # uid = part_data[0].decode().split()[1]
        msg = email.message_from_bytes(
            part_data[1], policy=email.policy.default
        )
        emails.append(msg)

    return emails


##### Watcher #####

def handle_one_new_email(email_msg: email.message.EmailMessage):
    print(f"{email_msg}")

def handle_new_emails(email_msg_list: list[email.message.EmailMessage]):
    print("-"*5 + " New Emails " + "-"*54)
    *msgs, last_msg = email_msg_list
    for msg in msgs:
        msg_id = msg["Message-ID"]
        print(f"~~~~~ START of {msg_id} ~~~~~")
        handle_one_new_email(msg)
        print(f"~~~~~ END of {msg_id} ~~~~~")
    handle_one_new_email(last_msg)
    print("-"*71)

def imap4_idle_loop(imap_handler: IMAP4, mailbox: str):
    uids_prev = fetchall_email_uid(imap_handler, mailbox)
    if uids_prev is None:
        # error(f"Failed to fetch all email uids in '{mailbox}' (init)")
        uids_prev = []

    debug(f"imap4_idle_loop: uids_init={uids_prev}")

    if uids_prev:
        emails = fetch_emails_by_uids(imap_handler, uids_prev)
        emails and handle_new_emails(emails)

    while True:
        with imap_handler.idle(29*60) as idler:
            _ = next(idler) # blocking
        uids_latest = fetchall_email_uid(imap_handler, mailbox)
        if uids_latest is None:
            error(f"Failed to fetch all email uids in '{mailbox}' (latest)")
            continue

        debug(f"imap4_idle_loop: uids_latest={uids_latest}")

        new_uids = list(set(uids_latest) - set(uids_prev))
        debug(f"imap4_idle_loop: new_uids={new_uids}")

        if new_uids:
            emails = fetch_emails_by_uids(imap_handler, new_uids)
            emails and handle_new_emails(emails)

        uids_prev = uids_latest

def watch_emails(
    host: str,
    port: int,
    user: str,
    passwd: str,
    mailbox: str = "INBOX"
) -> bool:
    with IMAP4_SSL(host, port) as imap_handler:
        # FIXME: maybe some exceptions raised if the authentication failed
        imap_handler.login(user, passwd)
        info("Logged in succeded")

        mailbox_enc = imap_encode(mailbox)
        debug(f"Encoded mailbox name: {mailbox_enc}")
        imap_handler.select(mailbox_enc)

        info(f"Watching mailbox '{mailbox}'")
        imap4_idle_loop(imap_handler, mailbox_enc)

        imap_handler.logout()
        info("Logged out")

    return True


##### CLI #####

def parse_args() -> argparse.Namespace | None:
    parser = argparse.ArgumentParser(
        description="Email watcher using IMAP",
        add_help=False,
        exit_on_error=False
    )

    parser.add_argument("--help", action="help", default=argparse.SUPPRESS,
        help="show this help"
    )

    parser.add_argument(
        "-h, --host", metavar="HOST", dest="host", type=str, required=True,
        help="specify IMAP server"
    )
    parser.add_argument(
        "-p", "--port", metavar="PORT", dest="port", type=int, required=True,
        help="specify IMAP server port"
    )
    parser.add_argument(
        "-u", "--user", metavar="USER", dest="user", type=str, required=True,
        help="specify Login user"
    )
    parser.add_argument(
        "-P", "--passwd", metavar="PASSWD_FILE", dest="passwd_file", type=Path,
        required=True, help="specify a file that contains login password"
    )
    parser.add_argument(
        "--mailbox", metavar="MAILBOX", dest="mailbox", type=str,
        required=False, default="INBOX", help="specify a mailbox name to watch"
    )

    args = None
    try:
        args = parser.parse_args()
    except argparse.ArgumentError as e:
        error(f"{e}")

    return args

def main() -> bool:
    args = parse_args()
    if not args:
        return False

    debug(f"Args: {args}")

    passwd: str | None = None
    with args.passwd_file.open("r") as fp:
        passwd = fp.read().strip()

    if passwd is None:
        error("Password is empty")
        return False

    status = True
    status = watch_emails(
        args.host,
        args.port,
        args.user,
        passwd,
        args.mailbox
    )

    return status


def cli() -> int:
    exit_status = 0
    try:
        if not main():
            exit_status = 1
    except KeyboardInterrupt:
        exit_status = 130    # 128 + SIGINT
    except Exception as e:
        error(f"{e}")
        print(f"{traceback.format_exc()}", file=sys.stderr)
        exit_status = 1
    finally:
        return exit_status


if __name__ == "__main__":
    sys.exit(cli())
