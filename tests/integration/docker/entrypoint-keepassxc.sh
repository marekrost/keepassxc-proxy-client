#!/bin/bash
# Launch KeePassXC against the test fixture.
#
# The fixture kdbx is mounted read-only at /fixtures/test.kdbx. We copy it to a
# writable location because KeePassXC rewrites the file on save / when settings
# change. Browser Integration is enabled via a pre-seeded config that lives at
# ~/.config/keepassxc/keepassxc.ini (mounted from the image / created on first
# run below).

set -euo pipefail

CONFIG_DIR="$HOME/.config/keepassxc"
DB_DIR="$HOME/db"
DB_PATH="$DB_DIR/test.kdbx"

mkdir -p "$CONFIG_DIR" "$DB_DIR"

# Seed a minimal config that turns Browser Integration on. KeePassXC writes
# many more keys on first run; we only need the Browser block.
if [ ! -f "$CONFIG_DIR/keepassxc.ini" ]; then
    cat > "$CONFIG_DIR/keepassxc.ini" <<'EOF'
[Browser]
Enabled=true
UpdateBinaryPath=false

[General]
ConfigVersion=2
EOF
fi

# Refresh the working copy of the fixture every container start so tests have a
# clean slate.
if [ -f /fixtures/test.kdbx ]; then
    cp /fixtures/test.kdbx "$DB_PATH"
fi

# `--pw-stdin` reads the master password from stdin so the test runner can
# unlock the DB without human input on each container start. The human still
# has to click "Allow" in the Browser Integration association dialog the first
# time, via noVNC at http://localhost:6080.
exec /usr/bin/keepassxc --pw-stdin "$DB_PATH" <<<"test"
