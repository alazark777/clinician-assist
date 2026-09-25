#!/usr/bin/env bash
set -Eeuo pipefail

KIT_ROOT="${CLINICIAN_KIT_ROOT:-/Users/alk/Desktop/cc-data-science/Learning/clinician-assist/clinician-assistant-kit}"
RUNTIME_DIR="$KIT_ROOT/var/runtime"
LOG_DIR="$RUNTIME_DIR/logs"
PID_DIR="$RUNTIME_DIR/pids"
AGENT_DIR="$KIT_ROOT/agent-service"
RECORDS_DIR="$KIT_ROOT/records-mcp"
WEB_DIR="$KIT_ROOT/web"
COMPOSE_FILE="$AGENT_DIR/observability/compose.yaml"
COMPOSE_ENV="$AGENT_DIR/observability/images.env"
OTLP_ENDPOINT="http://127.0.0.1:4318"

log() { printf '[clinician-stack] %s\n' "$*"; }
fail() { printf '[clinician-stack] ERROR: %s\n' "$*" >&2; exit 1; }
require() { command -v "$1" >/dev/null 2>&1 || fail "Missing command: $1"; }

pid_file() { printf '%s/%s.pid' "$PID_DIR" "$1"; }
log_file() { printf '%s/%s.log' "$LOG_DIR" "$1"; }

is_managed_running() {
  local file
  file="$(pid_file "$1")"
  [[ -f "$file" ]] && kill -0 "$(cat "$file")" 2>/dev/null
}

http_status() {
  curl --silent --output /dev/null --write-out '%{http_code}' --max-time 2 "$1" 2>/dev/null || true
}

wait_for_status() {
  local name="$1" url="$2" expected="$3" attempts="${4:-90}" status
  for ((i = 1; i <= attempts; i++)); do
    status="$(http_status "$url")"
    [[ "$status" =~ $expected ]] && return 0
    sleep 1
  done
  fail "$name did not become ready at $url; inspect $(log_file "$name")"
}

port_owner() {
  lsof -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null | tr '\n' ' '
}

ensure_free_or_healthy() {
  local name="$1" port="$2" url="$3" expected="$4" owner status
  owner="$(port_owner "$port")"
  [[ -z "$owner" ]] && return 0
  status="$(http_status "$url")"
  if [[ "$status" =~ $expected ]]; then
    log "$name already healthy on port $port (reusing)"
    return 1
  fi
  fail "Port $port is occupied by PID(s) $owner but $name is not healthy"
}

start_podman() {
  require podman
  if ! podman machine inspect >/dev/null 2>&1; then
    log "Initializing Podman machine"
    podman machine init
  fi
  if ! podman info >/dev/null 2>&1; then
    log "Starting Podman machine"
    podman machine start
  fi
  podman info >/dev/null 2>&1 || fail "Podman machine is unavailable"
  podman compose version >/dev/null 2>&1 ||
    fail "Podman Compose unavailable; install it with: brew install podman-compose"
}

start_observability() {
  ensure_free_or_healthy "jaeger" 16686 "http://127.0.0.1:16686/" '200|302' || return 0
  log "Starting OpenTelemetry collector and Jaeger with Podman"
  podman compose -f "$COMPOSE_FILE" --env-file "$COMPOSE_ENV" up -d
  wait_for_status "jaeger" "http://127.0.0.1:16686/" '200|302' 120
}

spawn_service() {
  local name="$1" workdir="$2"
  shift 2
  log "Starting $name"
  (
    cd "$workdir"
    nohup "$@" >>"$(log_file "$name")" 2>&1 &
    printf '%s\n' "$!" >"$(pid_file "$name")"
  )
}

start_records() {
  ensure_free_or_healthy "records-mcp" 8001 "http://127.0.0.1:8001/mcp" '401|405' || return 0
  [[ -f "$RECORDS_DIR/secrets/mcp-verification-key.pem" ]] ||
    fail "Missing records MCP verification key; run records-mcp/scripts/generate_dev_keys.sh"
  spawn_service records-mcp "$RECORDS_DIR" env \
    PATIENT_DATA_DIR=data/patients \
    MCP_VERIFICATION_KEY=secrets/mcp-verification-key.pem \
    MCP_TOKEN_ISSUER=clinician-agent-api \
    MCP_TOKEN_AUDIENCE=clinician-records-mcp \
    MCP_ALLOWED_ORIGINS=http://127.0.0.1:8000 \
    OTEL_EXPORTER_OTLP_ENDPOINT="$OTLP_ENDPOINT" \
    uv run python -m clinician_records --host 127.0.0.1 --port 8001
  wait_for_status "records-mcp" "http://127.0.0.1:8001/mcp" '401|405'
}

start_agent() {
  ensure_free_or_healthy "agent-service" 8000 "http://127.0.0.1:8000/health/ready" '200' || return 0
  [[ -f "$AGENT_DIR/.env" ]] || fail "Missing agent-service/.env"
  [[ -f "$RECORDS_DIR/secrets/mcp-signing-key.pem" ]] ||
    fail "Missing paired MCP signing key; run records-mcp/scripts/generate_dev_keys.sh"
  spawn_service agent-service "$AGENT_DIR" env \
    OTEL_EXPORTER_OTLP_ENDPOINT="$OTLP_ENDPOINT" \
    uv run uvicorn clinician_agent.main:app --host 127.0.0.1 --port 8000 --workers 1
  wait_for_status "agent-service" "http://127.0.0.1:8000/health/ready" '200'
}

start_web() {
  ensure_free_or_healthy "web" 5173 "http://127.0.0.1:5173/" '200' || return 0
  [[ -d "$WEB_DIR/node_modules" ]] || (cd "$WEB_DIR" && npm install)
  [[ -f "$WEB_DIR/.env" ]] ||
    printf 'VITE_AGENT_API_BASE_URL=http://127.0.0.1:8000\n' >"$WEB_DIR/.env"
  spawn_service web "$WEB_DIR" npm run dev -- --host 127.0.0.1 --port 5173
  wait_for_status "web" "http://127.0.0.1:5173/" '200'
}

stop_service() {
  local name="$1" file pid
  file="$(pid_file "$name")"
  [[ -f "$file" ]] || return 0
  pid="$(cat "$file")"
  if kill -0 "$pid" 2>/dev/null; then
    log "Stopping $name (PID $pid)"
    kill "$pid"
    for _ in {1..20}; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.25
    done
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$file"
}

status() {
  printf '%-16s %s\n' "records-mcp" "$(http_status http://127.0.0.1:8001/mcp)"
  printf '%-16s %s\n' "agent-service" "$(http_status http://127.0.0.1:8000/health/ready)"
  printf '%-16s %s\n' "web" "$(http_status http://127.0.0.1:5173/)"
  printf '%-16s %s\n' "jaeger" "$(http_status http://127.0.0.1:16686/)"
}

start_all() {
  require curl
  require lsof
  require uv
  require npm
  mkdir -p "$LOG_DIR" "$PID_DIR"
  [[ -d "$KIT_ROOT" ]] || fail "Kit not found: $KIT_ROOT"
  start_podman
  start_observability
  start_records
  start_agent
  start_web
  log "Ready"
  log "Web UI:    http://127.0.0.1:5173"
  log "Agent API: http://127.0.0.1:8000"
  log "MCP:       http://127.0.0.1:8001/mcp"
  log "Jaeger UI: http://127.0.0.1:16686"
}

stop_all() {
  mkdir -p "$LOG_DIR" "$PID_DIR"
  stop_service web
  stop_service agent-service
  stop_service records-mcp
  if command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then
    log "Stopping observability containers"
    podman compose -f "$COMPOSE_FILE" --env-file "$COMPOSE_ENV" down
  fi
}

show_logs() {
  mkdir -p "$LOG_DIR"
  for name in records-mcp agent-service web; do
    printf '\n== %s ==\n' "$name"
    [[ -f "$(log_file "$name")" ]] && tail -n 30 "$(log_file "$name")" || printf 'No log yet\n'
  done
}

case "${1:-start}" in
  start) start_all ;;
  stop) stop_all ;;
  restart) stop_all; start_all ;;
  status) status ;;
  logs) show_logs ;;
  *) fail "Usage: $0 {start|stop|restart|status|logs}" ;;
esac
