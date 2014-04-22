#!/bin/bash

if [ "$#" -eq 1 ]; then
	SSH_ARG="$1"
	SSH_DISP=':0'
elif [ "$#" -eq 2 ]; then
	SSH_ARG="$1"
	SSH_DISP="$2"
else
	exit 1
fi

LOCAL_RES="`xrandr 2>&1 | grep -Po 'current \d+ x \d+' | head -1 | grep -Po '\d+'`"
LOCAL_RES_X=`head -1 <<< "$LOCAL_RES"`
LOCAL_RES_Y=`tail -1 <<< "$LOCAL_RES"`


if [ "$DEBUG" = true ]; then for i in SSH_ARG SSH_DISP LOCAL_RES LOCAL_RES_X LOCAL_RES_Y; do
	eval "echo \"$i=\$$i\""
	echo
done; fi


ssh "$SSH_ARG" "export DEBUG='$DEBUG' && eXtend_alpha_server $LOCAL_RES_X $LOCAL_RES_Y $SSH_DISP"

