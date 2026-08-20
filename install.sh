#!/usr/bin/env bash
# install.sh — caveman installer for project-bedrock
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/robotaitai/project-bedrock/main/install.sh | bash
#
# Installs the `bedrock` CLI using whichever tool is available:
#   uv tool install  (preferred — isolated, fast)
#   pipx install     (good — isolated)
#   pip install      (fallback)

set -euo pipefail

PACKAGE="project-bedrock"
MIN_PYTHON="3.9"

# ── colors ──────────────────────────────────────────────────────────────────
if [ -t 1 ]; then
  BOLD="\033[1m"; GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; RESET="\033[0m"
else
  BOLD=""; GREEN=""; YELLOW=""; RED=""; RESET=""
fi

info()    { echo -e "${BOLD}${GREEN}=>${RESET} $*"; }
warn()    { echo -e "${BOLD}${YELLOW}!${RESET}  $*"; }
error()   { echo -e "${BOLD}${RED}error:${RESET} $*" >&2; exit 1; }
section() { echo -e "\n${BOLD}$*${RESET}"; }

# ── check Python ────────────────────────────────────────────────────────────
check_python() {
  local py
  for py in python3 python; do
    if command -v "$py" &>/dev/null; then
      local ver
      ver=$("$py" -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>/dev/null)
      if python3 -c "import sys; sys.exit(0 if sys.version_info >= (${MIN_PYTHON/./,}) else 1)" 2>/dev/null; then
        echo "$py"
        return 0
      fi
    fi
  done
  return 1
}

# ── purge legacy installs ────────────────────────────────────────────────────
# The distribution was renamed (agent-knowledge -> agent-knowledge-cli ->
# project-bedrock). Every version ships the same 'agent_knowledge' package and
# 'bedrock' script, so a leftover old dist shadows this one and the user keeps
# running stale code. Remove them across every installer before installing.
LEGACY_NAMES="agent-knowledge agent-knowledge-cli"

purge_legacy() {
  local found=0 p
  if command -v pipx &>/dev/null; then
    for p in $LEGACY_NAMES; do
      if pipx list --short 2>/dev/null | grep -q "^$p "; then
        warn "Removing legacy pipx install: $p"; pipx uninstall "$p" >/dev/null 2>&1 || true; found=1
      fi
    done
  fi
  if command -v uv &>/dev/null; then
    for p in $LEGACY_NAMES; do
      if uv tool list 2>/dev/null | grep -q "^$p "; then
        warn "Removing legacy uv tool: $p"; uv tool uninstall "$p" >/dev/null 2>&1 || true; found=1
      fi
    done
  fi
  if command -v pip3 &>/dev/null || command -v pip &>/dev/null; then
    local PIP; PIP=$(command -v pip3 || command -v pip)
    for p in $LEGACY_NAMES; do
      if "$PIP" show "$p" &>/dev/null; then
        warn "Removing legacy pip install: $p"; "$PIP" uninstall -y "$p" >/dev/null 2>&1 || true; found=1
      fi
    done
  fi
  [ "$found" -eq 1 ] && info "Cleaned up legacy install(s)."
  return 0
}

# ── install ──────────────────────────────────────────────────────────────────
section "project-bedrock installer"
echo "  installs the 'bedrock' CLI for AI agent project memory"
echo ""

PY=$(check_python) || error "Python ${MIN_PYTHON}+ is required. Install from https://python.org"
info "Python: $($PY --version)"

purge_legacy

if command -v uv &>/dev/null; then
  info "Using uv (isolated install)"
  uv tool install "$PACKAGE" --upgrade
  METHOD="uv tool"

elif command -v pipx &>/dev/null; then
  info "Using pipx (isolated install)"
  pipx install "$PACKAGE" --force
  METHOD="pipx"

elif command -v pip3 &>/dev/null || command -v pip &>/dev/null; then
  PIP=$(command -v pip3 || command -v pip)
  warn "uv and pipx not found — falling back to pip (not isolated)"
  warn "For a cleaner install: https://docs.astral.sh/uv/ or pip install pipx"
  "$PIP" install --upgrade "$PACKAGE"
  METHOD="pip"

else
  error "No installer found. Install uv (https://docs.astral.sh/uv/), pipx, or pip."
fi

# ── verify ───────────────────────────────────────────────────────────────────
echo ""
if command -v bedrock &>/dev/null; then
  VER=$(bedrock --version 2>/dev/null | head -1)
  info "Installed: ${VER} (via ${METHOD})"
else
  warn "'bedrock' not found on PATH after install."
  if [ "$METHOD" = "pipx" ]; then
    warn "Run: pipx ensurepath && source ~/.bashrc (or restart your shell)"
  elif [ "$METHOD" = "uv tool" ]; then
    warn "Run: uv tool update-shell && restart your shell"
  fi
  exit 1
fi

# ── next steps ───────────────────────────────────────────────────────────────
echo ""
section "Next steps"
echo "  cd your-project"
echo "  bedrock init"
echo ""
echo "  Then open the project in Claude Code or Cursor."
echo "  The agent will have persistent memory automatically."
echo ""
echo "  bedrock --help    for all commands"
echo "  bedrock view      to see your knowledge as a site"
