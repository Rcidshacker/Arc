#!/bin/bash
# Runs after every Edit/Write. Auto-formats the saved file.

FILE="$1"
[ -z "$FILE" ] && exit 0

case "$FILE" in
  *.py)
    ruff format "$FILE" 2>/dev/null
    ;;
  *.ts|*.tsx)
    # Run from mobile/ dir if the file is in mobile/
    if [[ "$FILE" == *"/mobile/"* ]]; then
      cd mobile && npx eslint "$FILE" --fix --quiet 2>/dev/null; cd ..
    fi
    ;;
esac

exit 0
