#!/bin/python

import codecs
import email
import email.policy
import sys
import traceback
from collections.abc import Generator


def read_text_iter(delim:str="\0") -> Generator[str]:
    def read_bytes_iter() -> Generator[bytes]:
        while True:
            yield sys.stdin.buffer.read1() # ty: ignore[unresolved-attribute]

    remaining_str = ""
    for text in codecs.iterdecode(read_bytes_iter(), "utf-8"):
        remaining_str += text
        chunk_list = remaining_str.split(delim)

        if len(chunk_list) > 0:
            remaining_str = chunk_list.pop()

        yield from chunk_list


def main():
    for raw_email_body in read_text_iter("\0"):
        body = email.message_from_string(
            raw_email_body,
            policy=email.policy.EmailPolicy(utf8=True)
        )

        subject = body.get("Subject")
        from_addr = body.get("From")

        print(f"{subject} ({from_addr})")

    return True


if __name__ == "__main__":
    exit_status = 0
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}\n{traceback.format_exc()}")
        exit_status = 1
    finally:
        sys.exit(exit_status)
