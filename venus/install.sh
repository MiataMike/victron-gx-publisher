#!/bin/sh
set -eu

APP_DIR=/data/victron-gx-publisher
RC_LOCAL=/data/rc.local
HOOK='# victron-gx-publisher'

if [ "$(cd "$(dirname "$0")/.." && pwd)" != "$APP_DIR" ]
then
    echo "Clone this repository to $APP_DIR before installing." >&2
    exit 1
fi

command -v python3 >/dev/null 2>&1 || {
    echo "Venus OS Python 3 was not found." >&2
    exit 1
}

chmod 755 "$APP_DIR"/venus/*.sh
mkdir -p "$APP_DIR/output" "$APP_DIR/run" "$APP_DIR/secrets"
chmod 700 "$APP_DIR/secrets"

if [ ! -e "$RC_LOCAL" ]
then
    printf '%s\n' '#!/bin/sh' > "$RC_LOCAL"
    chmod 755 "$RC_LOCAL"
fi

if ! grep -qF "$HOOK" "$RC_LOCAL"
then
    {
        printf '\n%s\n' "$HOOK"
        printf '%s\n' "$APP_DIR/venus/start.sh"
    } >> "$RC_LOCAL"
fi

"$APP_DIR/venus/start.sh"
echo "Installed. Use: logread -f | grep victron-gx"
