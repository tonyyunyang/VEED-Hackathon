#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# start.sh — Launch all VEED Hackathon services in a single terminal
#   1. Frontend   (Vite)            → http://localhost:5173
#   2. Server     (FastAPI)         → http://localhost:8000
#   3. FaceFusion (FastAPI)         → http://localhost:8001
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# ── Colors ────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
RESET='\033[0m'

PIDS=()

cleanup() {
    echo ""
    echo -e "${BOLD}${YELLOW}Shutting down all services...${RESET}"
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
        fi
    done
    wait 2>/dev/null
    echo -e "${BOLD}${GREEN}All services stopped.${RESET}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# ── Prefixed log helper ──────────────────────────────────────────────
# Usage: run_with_prefix COLOR LABEL COMMAND...
run_with_prefix() {
    local color="$1" label="$2"
    shift 2
    "$@" 2>&1 | while IFS= read -r line; do
        echo -e "${color}[${label}]${RESET} ${line}"
    done &
    # The PID of the pipe background job
    PIDS+=($!)
}

# ── Banner ────────────────────────────────────────────────────────────
echo -e "${BOLD}${CYAN}"
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║          VEED Hackathon — Starting Up            ║"
echo "  ╠══════════════════════════════════════════════════╣"
echo "  ║  Frontend      → http://localhost:5173           ║"
echo "  ║  Server         → http://localhost:8000          ║"
echo "  ║  FaceFusion API → http://localhost:8001          ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo -e "${RESET}"

# ── 1. Backend server ────────────────────────────────────────────────
echo -e "${GREEN}Starting server...${RESET}"
run_with_prefix "$GREEN" "server" \
    bash -c "cd '${ROOT_DIR}/server' && UV_CACHE_DIR='${ROOT_DIR}/.uv-cache' uv run uvicorn main:app --port 8000 --reload"

# ── 2. FaceFusion API ────────────────────────────────────────────────
FACEFUSION_DIR="${ROOT_DIR}/facefusion-VEED"
FACEFUSION_VENV="${FACEFUSION_DIR}/.venv/bin/python"

if [ -f "$FACEFUSION_VENV" ]; then
    echo -e "${BLUE}Starting FaceFusion API...${RESET}"
    run_with_prefix "$BLUE" "facefusion" \
        bash -c "cd '${FACEFUSION_DIR}' && '${FACEFUSION_VENV}' api.py"
else
    echo -e "${RED}FaceFusion venv not found at ${FACEFUSION_VENV} — skipping${RESET}"
fi

# ── 3. Frontend dev server ───────────────────────────────────────────
echo -e "${CYAN}Starting frontend...${RESET}"
run_with_prefix "$CYAN" "frontend" \
    bash -c "cd '${ROOT_DIR}' && npx vite --host 127.0.0.1"

echo ""
echo -e "${BOLD}${GREEN}All services launched. Press Ctrl+C to stop.${RESET}"
echo ""

# Wait for all background processes
wait
