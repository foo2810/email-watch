#!/bin/python

"""
Run: email-watch -h <IMAP server> -p <port> -u <username or email address> -P <password file> 2>/dev/null | ./watch-emails.py
"""

from __future__ import annotations

import email
import email.policy
import sys


def main():
    remaining_str = ""

    while True:
        input_binary = sys.stdin.buffer.read1()

        if len(input_binary) == 0:
            continue

        input_str = input_binary.decode("utf-8")
        input_str = remaining_str + input_str
        remaining_str = ""

        if input_str[-1] == "\0":
            input_str = input_str[:-1]
        else:
            last_nul_pos = input_str.rfind("\0")
            # If NUL character is not included, append whole `input_str` to
            # `remaining_str`. In this case, since `rfind` returns -1, checking
            # the return value is not necessary.
            remaining_str += input_str[last_nul_pos+1:]
            input_str = input_str[:last_nul_pos+1]

        chunks = input_str.split("\0")
        for chunk in chunks:
            if len(chunk) == 0:
                continue

            raw_email_body = chunk
            body = email.message_from_string(
                raw_email_body,
                policy=email.policy.EmailPolicy(utf8=True)
            )

            subject = body.get("Subject")
            from_addr = body.get("From")

            print(f"{subject} ({from_addr})")


if __name__ == "__main__":
    exit_status = 0
    try:
        main()
    except KeyboardInterrupt:
        exit_status = 130
    except Exception as e:
        import traceback
        print(f"Error: {e}\n{traceback.format_exc()}")
        exit_status = 1
    finally:
        sys.exit(exit_status)
