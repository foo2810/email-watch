# email-watch

*email-watch* watches emails using IMAP protocol.


## Build and Install

```
$ uv build

$ uv tool install dist/email_watch-<version>-py3-none-any.whl
```


## How to use

Example (gmail)
```
$ email-watch -h imap.gmail.com -p 993 -u <your usename>@gmail.com -P <password file> --mailbox INBOX --ssl
```
`<password file>` contains an **application password** to authorize your gmail account.

An application password is not the same as your Google Account password.
Please see https://support.google.com/mail/answer/185833 for details.

If you want to use OAuth for authentication, please use an email OAuth proxy (e.g. [email-oauth2-proxy](https://github.com/simonrob/email-oauth2-proxy)).

This tool outputs data for emails newly added to `MAILBOX`. Each email is represented in RFC 5322 Internet Message Format, and consecutive emails are separated by a NULL character.


## Eamples

Please see the *examples* directory for sample scripts.
