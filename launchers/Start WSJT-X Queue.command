#!/bin/sh
cd "$(dirname "$0")" || exit 1
./wsjtx-queue
printf '\nWSJT-X Queue has exited. You can close this window.\n'
printf 'Press Return to close... '
read _
