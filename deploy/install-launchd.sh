#!/usr/bin/env bash
# Install the flickrfinder LaunchAgent. Idempotent: safe to re-run.
#
# Result: ~/Library/LaunchAgents/com.flickrfinder.server.plist is loaded into
# launchd, runs at login, restarts on crash, logs to data/flickrfinder.log,
# and binds the server to 0.0.0.0 so the LAN can reach it.

set -euo pipefail

# Repo root = parent of this script's directory.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.flickrfinder.server"
PLIST_SRC="$REPO/deploy/com.flickrfinder.server.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"

# Sanity checks
if [[ ! -x "$REPO/.venv/bin/flickrfinder" ]]; then
  echo "✗ $REPO/.venv/bin/flickrfinder is missing or not executable."
  echo "  Run 'uv sync' in $REPO first." >&2
  exit 1
fi
if [[ ! -f "$REPO/src/flickrfinder/web/index.html" ]]; then
  echo "! Web UI not built yet. The API will still serve, but the SPA at /"
  echo "  will show a build hint. To build it, run:"
  echo "    cd $REPO/web && bun install && bun run build"
fi

mkdir -p "$REPO/data" "$HOME/Library/LaunchAgents"

# Render the plist with __REPO__ substituted.
sed "s|__REPO__|$REPO|g" "$PLIST_SRC" > "$PLIST_DST"
echo "✓ Wrote $PLIST_DST"

# If it's already loaded, unload first (otherwise launchctl bootstrap errors).
DOMAIN="gui/$(id -u)"
TARGET="$DOMAIN/$LABEL"
if launchctl print "$TARGET" >/dev/null 2>&1; then
  launchctl bootout "$TARGET" || true
  echo "✓ Unloaded previous instance"
fi

launchctl bootstrap "$DOMAIN" "$PLIST_DST"
launchctl kickstart -k "$TARGET" || true
echo "✓ Loaded and kickstarted $LABEL"

# Wait briefly and report status.
sleep 2
if launchctl print "$TARGET" >/dev/null 2>&1; then
  echo
  launchctl print "$TARGET" | grep -E "state|last exit code|pid" | head -5
fi

cat <<EOF

Done. The server is now running under launchd.
  Logs:   tail -f $REPO/data/flickrfinder.log
  Stop:   launchctl bootout $TARGET
  Start:  launchctl bootstrap $DOMAIN $PLIST_DST
  Status: launchctl print $TARGET
EOF
