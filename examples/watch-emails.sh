#!/bin/bash

EMAIL_WATCH="email-watch -h <IMAP server> -p <port> -u <username or email address> -P <password file>"

${EMAIL_WATCH} 2>/dev/null | while read -r -d "" email_body; do
	echo "${email_body}" | grep -e "Subject:"
	# echo "${email_body}" | <another script> ...
done
