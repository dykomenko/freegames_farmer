#!/bin/bash
set -e

INSTALL_DIR="$HOME/freegames_farmer"

echo "=== Installing freegames_farmer ==="

mkdir -p "$INSTALL_DIR"
cp farmer.py config.json requirements.txt "$INSTALL_DIR/"

# Create venv and install deps
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# Init claimed.json
[ -f "$INSTALL_DIR/claimed.json" ] || echo "[]" > "$INSTALL_DIR/claimed.json"

# Create systemd user timer (runs daily at 12:00)
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/freegames-farmer.service << EOF
[Unit]
Description=Free Games Farmer - claim free Steam games via ASF

[Service]
Type=oneshot
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/farmer.py
EOF

cat > ~/.config/systemd/user/freegames-farmer.timer << EOF
[Unit]
Description=Run Free Games Farmer once a day

[Timer]
OnBootSec=5min
OnCalendar=*-*-* 12:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now freegames-farmer.timer
loginctl enable-linger "$(whoami)" 2>/dev/null || true

echo ""
echo "=== Done ==="
echo "Config:  $INSTALL_DIR/config.json  (set asf_password!)"
echo "Timer:   daily at 12:00"
echo "Status:  systemctl --user status freegames-farmer.timer"
echo "Logs:    journalctl --user -u freegames-farmer.service"
echo "Test:    $INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/farmer.py"
