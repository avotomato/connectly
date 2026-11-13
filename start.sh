#!/usr/bin/env zsh
# Connectly — start the demo server
# Usage: ./start.sh [port]
#   default port: 8080

set -e

PORT="${1:-8080}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Create virtualenv if missing
if [ ! -d "venv" ]; then
  echo "Creating virtualenv..."
  python3 -m venv venv
  venv/bin/pip install -q flask flask-sqlalchemy
fi

# Init DB
mkdir -p data
venv/bin/python3 - <<'PYEOF'
from app import app, db
with app.app_context():
    db.create_all()
PYEOF

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║         Connectly Demo Server                ║"
echo "╠══════════════════════════════════════════════╣"
echo "║  Local:    http://localhost:${PORT}              ║"
echo "║  Network:  http://$(ipconfig getifaddr en0 2>/dev/null || hostname -I | awk '{print $1}'):${PORT}  ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "Press Ctrl+C to stop."
echo ""

FLASK_PORT=$PORT venv/bin/python3 -c "
import os
from app import app, db
port = int(os.environ.get('FLASK_PORT', 8080))
with app.app_context():
    db.create_all()
app.run(host='0.0.0.0', port=port, debug=False)
"
