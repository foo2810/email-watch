import argparse
import email.message
import sys
import traceback

from pathlib import Path

from .logging import error, debug, enable_debug_log
from .core import watch_emails


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
    parser.add_argument(
        "--ssl", dest="use_ssl", required=False, action="store_true",
        help="enable SSL"
    )
    parser.add_argument(
        "--debug", dest="debug", required=False, action="store_true",
        help="enable debug log"
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

    if args.debug:
        enable_debug_log()

    debug(f"Args: {args}")

    passwd: str | None = None
    with args.passwd_file.open("r") as fp:
        passwd = fp.read().strip()

    if passwd is None:
        error("Password is empty")
        return False

    def handle_one_new_email(email_msg: email.message.EmailMessage):
        print(f"{email_msg}", end="\0", flush=True)

    status = True
    status = watch_emails(
        args.host,
        args.port,
        args.use_ssl,
        args.user,
        passwd,
        args.mailbox,
        handle_one_new_email
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

    return exit_status


if __name__ == "__main__":
    sys.exit(cli())
