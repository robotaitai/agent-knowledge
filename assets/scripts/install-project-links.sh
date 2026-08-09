#!/bin/bash
#
# Connect a project repo to a dedicated knowledge folder through ./bedrock.
#
# Supported forms:
#   ./install-project-links.sh --slug <slug> --repo <repo-path>
#   ./install-project-links.sh --slug <slug> --repo <repo-path> --real-path <knowledge-path>
#   ./install-project-links.sh <repo-path> <knowledge-path>      # legacy form
#   ./install-project-links.sh <slug> <repo-path>                # slug + repo form
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENTS_RULES_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_TEMPLATE_DIR="$AGENTS_RULES_DIR/templates/project"
# Same template refresh-system installs, so init and refresh never disagree.
HOOK_TEMPLATE="$AGENTS_RULES_DIR/templates/integrations/cursor/hooks.json"

# shellcheck source=/dev/null
. "$SCRIPT_DIR/lib/knowledge-common.sh"

usage() {
    cat <<'EOF'
Usage:
  scripts/install-project-links.sh --slug <slug> --repo <repo-path> [--external] [--knowledge-home <dir>] [--real-path <dir>] [--install-hooks] [--dry-run] [--json] [--summary-file <file>]

Modes:
  default (local):  knowledge lives in ./bedrock/ (in the repo,
                    git-tracked). ~/agent-os/projects/<slug>/ is a symlink
                    pointing back to the repo folder.
  --external:       knowledge lives in ~/agent-os/projects/<slug>/,
                    ./bedrock is a symlink to that folder.

Notes:
  - Existing valid setup is left alone unless --force is provided.
  - --local is accepted as a no-op alias for backward compatibility.
EOF
}

PROJECT_SLUG_ARG=""
REPO_PATH=""
KNOWLEDGE_HOME="$HOME/agent-os/projects"
REAL_PATH_ARG=""
INSTALL_HOOKS=0
LOCAL_MODE=1
POSITIONAL=()
WARNINGS=()
CHANGES=()

while [ "$#" -gt 0 ]; do
    if kc_parse_common_flag "$@" ; then
        shift
        continue
    fi
    flag_status=$?
    if [ "$flag_status" -eq 2 ]; then
        shift 2
        continue
    fi

    case "$1" in
        --slug)
            PROJECT_SLUG_ARG="${2:-}"
            shift 2
            ;;
        --repo)
            REPO_PATH="${2:-}"
            shift 2
            ;;
        --knowledge-home)
            KNOWLEDGE_HOME="${2:-}"
            shift 2
            ;;
        --real-path)
            REAL_PATH_ARG="${2:-}"
            shift 2
            ;;
        --install-hooks)
            INSTALL_HOOKS=1
            shift
            ;;
        --local)
            LOCAL_MODE=1  # no-op: local is now the default; kept for backward compat
            shift
            ;;
        --external)
            LOCAL_MODE=0
            shift
            ;;
        *)
            POSITIONAL+=("$1")
            shift
            ;;
    esac
done

if [ "$SHOW_HELP" -eq 1 ]; then
    usage
    exit 0
fi

if [ -z "$REPO_PATH" ] && [ ${#POSITIONAL[@]} -eq 2 ]; then
    if [ -d "${POSITIONAL[0]}" ]; then
        REPO_PATH="${POSITIONAL[0]}"
        REAL_PATH_ARG="${POSITIONAL[1]}"
        PROJECT_SLUG_ARG="$(kc_slugify "$(basename "$REPO_PATH")")"
    else
        PROJECT_SLUG_ARG="${POSITIONAL[0]}"
        REPO_PATH="${POSITIONAL[1]}"
    fi
fi

[ -n "$REPO_PATH" ] || kc_fail "Missing repo path. See --help."
REPO_PATH="$(cd "$REPO_PATH" 2>/dev/null && pwd)"
[ -n "$REPO_PATH" ] || kc_fail "Unable to resolve repo path: $REPO_PATH"

if [ -z "$PROJECT_SLUG_ARG" ]; then
    PROJECT_SLUG_ARG="$(kc_slugify "$(basename "$REPO_PATH")")"
fi

if [ -z "$REAL_PATH_ARG" ]; then
    REAL_PATH_ARG="$KNOWLEDGE_HOME/$PROJECT_SLUG_ARG"
fi
REAL_PATH_ARG="$(kc_resolve_relative "$PWD" "$REAL_PATH_ARG")"

load_existing_state() {
    kc_load_project_context "$REPO_PATH"
}

load_existing_state

TARGET_PROJECT="$REPO_PATH"
PROJECT_NAME="$(basename "$TARGET_PROJECT")"
PROJECT_SLUG="$PROJECT_SLUG_ARG"
KNOWLEDGE_REAL_DIR="$REAL_PATH_ARG"
KNOWLEDGE_POINTER_PATH="$TARGET_PROJECT/bedrock"
POINTER_DISPLAY="./bedrock"
AGENT_PROJECT_FILE="$TARGET_PROJECT/.agent-project.yaml"
AGENTS_FILE="$TARGET_PROJECT/AGENTS.md"
IGNORE_FILE="$TARGET_PROJECT/.agentknowledgeignore"
CURSOR_DIR="$TARGET_PROJECT/.cursor"
CURSOR_HOOKS_FILE="$CURSOR_DIR/hooks.json"

kc_log "Connecting project: $TARGET_PROJECT"
kc_log "  slug: $PROJECT_SLUG"

if [ "$LOCAL_MODE" -eq 1 ]; then
    # ── Local mode: knowledge lives in the repo, agent-os symlink points back ──
    KNOWLEDGE_REAL_DIR="$TARGET_PROJECT/bedrock"
    kc_log "  mode: local (knowledge in repo)"
    kc_log "  real knowledge path: $KNOWLEDGE_REAL_DIR"

    # Create ./bedrock/ as a real directory
    kc_ensure_dir "$KNOWLEDGE_REAL_DIR" "bedrock/"
    case "$KC_LAST_ACTION" in
        created|would-create)
            CHANGES+=("knowledge-dir")
            ;;
    esac

    # Create the reversed symlink: ~/agent-os/projects/<slug>/ → ./bedrock/
    AGENT_OS_LINK="$KNOWLEDGE_HOME/$PROJECT_SLUG"
    if [ "$DRY_RUN" -eq 0 ]; then
        if [ ! -e "$AGENT_OS_LINK" ] && [ ! -L "$AGENT_OS_LINK" ]; then
            mkdir -p "$(dirname "$AGENT_OS_LINK")"
            ln -s "$KNOWLEDGE_REAL_DIR" "$AGENT_OS_LINK"
            kc_log "  linked: $AGENT_OS_LINK -> $KNOWLEDGE_REAL_DIR"
            CHANGES+=("agent-os-link")
        elif [ -L "$AGENT_OS_LINK" ]; then
            kc_log "  exists: $AGENT_OS_LINK (symlink left unchanged)"
        fi
    else
        kc_log "  [dry-run] would link: $AGENT_OS_LINK -> $KNOWLEDGE_REAL_DIR"
    fi
else
    # ── External mode (default): knowledge in agent-os, repo has symlink ──
    kc_log "  real knowledge path: $KNOWLEDGE_REAL_DIR"

    symlink_caveat="$(kc_detect_symlink_caveat)"
    if [ -n "$symlink_caveat" ]; then
        WARNINGS+=("$symlink_caveat")
        kc_log "  caveat: $symlink_caveat"
    fi

    kc_ensure_dir "$KNOWLEDGE_REAL_DIR" "${KNOWLEDGE_REAL_DIR#$HOME/}"
    case "$KC_LAST_ACTION" in
        created|would-create)
            CHANGES+=("knowledge-dir")
            ;;
    esac
    if [ -d "$KNOWLEDGE_REAL_DIR" ]; then
        KNOWLEDGE_REAL_DIR="$(cd "$KNOWLEDGE_REAL_DIR" 2>/dev/null && pwd -P)"
    fi

    kc_ensure_symlink "$KNOWLEDGE_REAL_DIR" "$KNOWLEDGE_POINTER_PATH" "bedrock"
    case "$KC_LAST_ACTION" in
        created|updated|would-create|would-update)
            CHANGES+=("pointer")
            ;;
    esac
fi

VAULT_MODE_VALUE="external"
REAL_PATH_VALUE="$KNOWLEDGE_REAL_DIR"
if [ "$LOCAL_MODE" -eq 1 ]; then
    VAULT_MODE_VALUE="local"
    # Local vaults always live at <repo>/bedrock. Record it relatively so the
    # tracked file stays valid on every machine that clones the repo.
    REAL_PATH_VALUE="./bedrock"
fi

if [ ! -f "$AGENT_PROJECT_FILE" ] || [ "$FORCE" -eq 1 ]; then
    kc_replace_in_template \
        "$PROJECT_TEMPLATE_DIR/.agent-project.yaml" \
        "$AGENT_PROJECT_FILE" \
        ".agent-project.yaml" \
        "<project-name>" "$PROJECT_NAME" \
        "<project-slug>" "$PROJECT_SLUG" \
        "<absolute-path-to-dedicated-knowledge-folder>" "$REAL_PATH_VALUE" \
        "<vault-mode>" "$VAULT_MODE_VALUE"
    case "$KC_LAST_ACTION" in
        created|updated|would-create|would-update)
            CHANGES+=(".agent-project.yaml")
            ;;
    esac
else
    kc_log "  exists: .agent-project.yaml (left unchanged)"
fi

if [ ! -f "$AGENTS_FILE" ] || [ "$FORCE" -eq 1 ]; then
    kc_copy_file "$PROJECT_TEMPLATE_DIR/AGENTS.md" "$AGENTS_FILE" "AGENTS.md"
    case "$KC_LAST_ACTION" in
        created|updated|would-create|would-update)
            CHANGES+=("AGENTS.md")
            ;;
    esac
else
    kc_log "  exists: AGENTS.md (left unchanged)"
fi

if [ ! -f "$TARGET_PROJECT/.gitignore" ]; then
    kc_copy_file "$PROJECT_TEMPLATE_DIR/gitignore.bedrock" "$TARGET_PROJECT/.gitignore" ".gitignore"
    case "$KC_LAST_ACTION" in
        created|updated|would-create|would-update)
            CHANGES+=(".gitignore")
            ;;
    esac
else
    kc_log "  note: existing .gitignore left unchanged"
fi

if [ ! -f "$IGNORE_FILE" ] || [ "$FORCE" -eq 1 ]; then
    kc_copy_file "$PROJECT_TEMPLATE_DIR/.agentknowledgeignore" "$IGNORE_FILE" ".agentknowledgeignore"
    case "$KC_LAST_ACTION" in
        created|updated|would-create|would-update)
            CHANGES+=(".agentknowledgeignore")
            ;;
    esac
else
    kc_log "  exists: .agentknowledgeignore (left unchanged)"
fi

if [ "$INSTALL_HOOKS" -eq 1 ]; then
    kc_ensure_dir "$CURSOR_DIR" ".cursor/"
    if [ ! -f "$CURSOR_HOOKS_FILE" ] || [ "$FORCE" -eq 1 ]; then
        # Hook commands use --project . -- they run with the repo root as cwd,
        # so no machine-specific path is baked into the tracked config.
        kc_copy_file "$HOOK_TEMPLATE" "$CURSOR_HOOKS_FILE" ".cursor/hooks.json"
        case "$KC_LAST_ACTION" in
            created|updated|would-create|would-update)
                CHANGES+=(".cursor/hooks.json")
                ;;
        esac
    else
        kc_log "  exists: .cursor/hooks.json (left unchanged)"
    fi
fi

if [ \( ! -f "$KNOWLEDGE_REAL_DIR/Memory/PROJECT.md" \) -a \( ! -f "$KNOWLEDGE_REAL_DIR/Memory/MEMORY.md" \) ] || [ ! -f "$KNOWLEDGE_REAL_DIR/STATUS.md" ] || [ "$FORCE" -eq 1 ]; then
    bootstrap_cmd="$SCRIPT_DIR/bootstrap-memory-tree.sh"
    bootstrap_args=(--project "$TARGET_PROJECT")
    if [ "$DRY_RUN" -eq 1 ]; then
        bootstrap_args+=(--dry-run)
    fi
    if [ -n "$SUMMARY_FILE" ]; then
        :
    fi
    kc_run_child_script "$bootstrap_cmd" "${bootstrap_args[@]}"
    CHANGES+=("bootstrap")
fi

json_summary="{"
json_summary="$json_summary\"script\":\"install-project-links\","
json_summary="$json_summary\"repo_root\":\"$(kc_json_escape "$TARGET_PROJECT")\","
json_summary="$json_summary\"project_slug\":\"$(kc_json_escape "$PROJECT_SLUG")\","
json_summary="$json_summary\"real_knowledge_path\":\"$(kc_json_escape "$KNOWLEDGE_REAL_DIR")\","
json_summary="$json_summary\"pointer_path\":\"$(kc_json_escape "$KNOWLEDGE_POINTER_PATH")\","
json_summary="$json_summary\"dry_run\":$(kc_json_bool "$DRY_RUN"),"
json_summary="$json_summary\"install_hooks\":$(kc_json_bool "$INSTALL_HOOKS"),"
json_summary="$json_summary\"changes\":$(kc_json_array "${CHANGES[@]+"${CHANGES[@]}"}"),"
json_summary="$json_summary\"warnings\":$(kc_json_array "${WARNINGS[@]+"${WARNINGS[@]}"}")"
json_summary="$json_summary}"
kc_write_json_output "$json_summary"
