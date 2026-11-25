import base64
import email
import email.message
import email.policy

from collections.abc import Callable
from imaplib import IMAP4, IMAP4_SSL
from typing import cast

from .logging import info, warn, error, debug


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

    data = None
    try:
        status, data = imap_handler.fetch("1:*", "UID")
    except IMAP4.error as e:
        error(f"fetchall_email_uid: `FETCH 1:* UID` failed: {e}")
        status = "BAD"

    debug(f"fetchall_email_uid: FETCH status: {status}")

    if status != "OK" or data is None:
        return None

    data_filed = cast(
        list[bytes],
        list(filter(
            lambda ent: ent is not None and isinstance(ent, bytes),
            data
        ))
    )

    # "<NUM> (UID <UID>)" --> <UID>
    def converter(ent: bytes) -> int:
        return int(ent.decode().split()[-1][:-1])

    uids = list(map(converter, data_filed))

    return uids


def fetch_emails_by_uids(
    imap_handler: IMAP4,
    uids: list[int]
) -> list[email.message.EmailMessage] | None:
    if not uids:
        return []

    uid_strs = list(map(str, uids))

    fetched_data = None
    try:
        # Use "BODY.PEEK" not to set SEEN flag to the fetched emails
        status, fetched_data = imap_handler.uid(
            "FETCH", ",".join(uid_strs), "(BODY.PEEK[])"
        )
    except IMAP4.error as e:
        error(f"fetch_emails_by_uids: FETCH command failed: {e}")
        status = "BAD"

    debug(f"fetch_emails_by_uids: FETCH status: {status}")

    if status != "OK" or fetched_data is None:
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


def idle_wait(imap_handler: IMAP4, timeout: int) -> bool:
    """
    Return true when valid responses exists, otherwise return False
    """
    if (timeout <= 0):
        raise ValueError("imap_wait: timeout must be positive")
    if (timeout > 29*60):
        warn("imap_wait: timeout is larger than 1740s. Keep timeout at most 1740s to avoid inactivity timeout on IMAP server") # noqa: E501

    with imap_handler.idle(timeout) as idler:
        try:
            _ = next(idler) # blocking
        except StopIteration:
            # When IDLE is timed out, the iterator raises StopIteration
            pass
        except Exception as e:
            error(f"imap_wait: {e}")
            return False

    return True


##### Watcher #####

def handle_new_emails(
    email_msg_list: list[email.message.EmailMessage],
    email_handler: Callable[[email.message.EmailMessage], None]
):
    for msg in email_msg_list:
        email_handler(msg)


def imap4_idle_loop(
    imap_handler: IMAP4,
    mailbox: str,
    email_handler: Callable[[email.message.EmailMessage], None]
):
    uids_prev = fetchall_email_uid(imap_handler, mailbox)
    if uids_prev is None:
        # error(f"Failed to fetch all email uids in '{mailbox}' (init)")
        uids_prev = []

    debug(f"imap4_idle_loop: uids_init={uids_prev}")

    if uids_prev:
        emails = fetch_emails_by_uids(imap_handler, uids_prev)
        if emails:
            handle_new_emails(emails, email_handler)

    while True:
        if not idle_wait(imap_handler, timeout=29*60):
            return False

        uids_latest = fetchall_email_uid(imap_handler, mailbox)
        if uids_latest is None:
            error(f"Failed to fetch all email uids in '{mailbox}' (latest)")
            continue

        debug(f"imap4_idle_loop: uids_latest={uids_latest}")

        new_uids = list(set(uids_latest) - set(uids_prev))
        debug(f"imap4_idle_loop: new_uids={new_uids}")

        if new_uids:
            emails = fetch_emails_by_uids(imap_handler, new_uids)
            if emails:
                handle_new_emails(emails, email_handler)

        uids_prev = uids_latest


def watch_emails(
    host: str,
    port: int,
    use_ssl: bool,
    user: str,
    passwd: str,
    mailbox: str,
    email_handler: Callable[[email.message.EmailMessage], None]
) -> bool:
    imap_class = IMAP4_SSL if use_ssl else IMAP4

    with imap_class(host, port) as imap_handler:
        # FIXME: maybe some exceptions raised if the authentication failed
        imap_handler.login(user, passwd)
        info("Logged in succeded")

        mailbox_enc = imap_encode(mailbox)
        debug(f"Encoded mailbox name: {mailbox_enc}")
        imap_handler.select(mailbox_enc)

        info(f"Watching mailbox '{mailbox}'")
        imap4_idle_loop(imap_handler, mailbox_enc, email_handler)

        imap_handler.logout()
        info("Logged out")

    return True


__all__ = ["watch_emails"]
