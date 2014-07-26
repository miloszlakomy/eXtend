#!/bin/bash

GUAC_USER_MAPPING='/etc/guacamole/user-mapping.xml'
GUAC_USER_ACCESS='666'

GUAC_USER_ACTUAL_ACCESS=`stat -c '%a'  "$GUAC_USER_MAPPING"`
if [ "$GUAC_USER_ACCESS" != "$GUAC_USER_ACTUAL_ACCESS" ]; then
    echo "- setting $GUAC_USER_MAPPING access rights to $GUAC_USER_ACCESS (was $GUAC_USER_ACTUAL_ACCESS)"
    chmod "$GUAC_USER_ACCESS" "$GUAC_USER_MAPPING"
fi

