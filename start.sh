#!/usr/bin/env bash
# ============================================================
#  AI Microdrama Studio - launcher (POSIX / WSL / git-bash)
#  Starts ComfyUI (if down, on Windows), the FastAPI backend,
#  and the Vite frontend. Backend/frontend run in the
#  background; logs go to ./logs, PIDs to ./logs/*.pid.
#
#  Usage:  bash start.sh      (or  chmod +x start.sh && ./start.sh)
#  Stop:   kill $(cat logs/backend.pid logs/frontend.pid)
# ============================================================
cd "$(dirname "$0")"
echo "=== AI Microdrama Studio ==="

COMFY_URL="${COMFY_URL:-http://localhost:8188}"
LLM_URL="${LLM_BASE_URL:-http://localhost:3000/v1}"
COMFY_ROOT="${COMFY_ROOT:-/c/Users/micke/Desktop/AI/ComfyUI}"

# microdrama env Python (override with MICRODRAMA_PY=/path/to/python)
PY="${MICRODRAMA_PY:-/c/Users/micke/anaconda3/envs/microdrama/python.exe}"
[ -x "$PY" ] || PY="$(command -v python || command -v python3)"

# 1) ComfyUI -------------------------------------------------
if ! curl -sf "$COMFY_URL/system_stats" >/dev/null 2>&1; then
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
      if [ -f "$COMFY_ROOT/start.bat" ]; then
        echo "[..] starting ComfyUI via start.bat"
        cmd //c start "" "$(cygpath -w "$COMFY_ROOT/start.bat")" 2>/dev/null || true
      else
        echo "[!] ComfyUI down and start.bat not found at $COMFY_ROOT"
      fi ;;
    *) echo "[!] ComfyUI not running at $COMFY_URL - start it manually." ;;
  esac
  printf "     waiting for ComfyUI"
  for _ in $(seq 1 60); do
    curl -sf "$COMFY_URL/system_stats" >/dev/null 2>&1 && { echo " up."; break; }
    printf "."; sleep 2
  done
else
  echo "[ok] ComfyUI already running."
fi

# 2) Director LLM -------------------------------------------
curl -sf "${LLM_URL%/v1}/" >/dev/null 2>&1 \
  || echo "[!] Director LLM ($LLM_URL) unreachable - start your gpt-5-mini server."

# 3) backend + frontend (background) ------------------------
mkdir -p logs
echo "[..] backend  -> http://localhost:8000  (logs/backend.log)"
nohup "$PY" -m uvicorn microdrama.backend.app:app --host 127.0.0.1 --port 8000 \
  > logs/backend.log 2>&1 &
echo $! > logs/backend.pid

echo "[..] frontend -> http://localhost:5173  (logs/frontend.log)"
( cd frontend && nohup npm run dev > ../logs/frontend.log 2>&1 & echo $! > ../logs/frontend.pid )

echo ""
echo "Studio:  http://localhost:5173"
echo "API:     http://localhost:8000/docs"
echo "Stop:    kill \$(cat logs/backend.pid logs/frontend.pid)"
