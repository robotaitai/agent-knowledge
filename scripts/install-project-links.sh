#!/bin/bash
#
# Connect a project repo to a dedicated knowledge folder through ./agent-knowledge.
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
HOOK_TEMPLATE="$AGENTS_RULES_DIR/templates/hooks/hooks.json.template"

# shellcheck source=/dev/null
. "$SCRIPT_DIR/lib/knowledge-common.sh"

usage() {
    cat <<'EOF'
Usage:
  scripts/install-project-links.sh --slug <slug> --repo <repo-path> [--knowledge-home <dir>] [--real-path <dir>] [--install-hooks] [--dry-run] [--json] [--summary-file <file>]

Notes:
  - The source of truth lives in the dedicated external knowledge folder.
  - The project repo exposes ./agent-knowledge as a local pointer to that folder.
  - Existing valid setup is left alone unless --force is provided.
EOF
}

PROJECT_SLUG_ARG=""
REPO_PATH=""
KNOWLEDGE_HOME="$HOME/agent-os/projects"
REAL_PATH_ARG=""
INSTALL_HOOKS=0
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
KNOWLEDGE_POINTER_PATH="$TARGET_PROJECT/agent-knowledge"
POINTER_DISPLAY="./agent-knowledge"
AGENT_PROJECT_FILE="$TARGET_PROJECT/.agent-project.yaml"
AGENTS_FILE="$TARGET_PROJECT/AGENTS.md"
IGNORE_FILE="$TARGET_PROJECT/.agentknowledgeignore"
CURSOR_DIR="$TARGET_PROJECT/.cursor"
CURSOR_HOOKS_FILE="$CURSOR_DIR/hooks.json"

kc_log "Connecting project: $TARGET_PROJECT"
kc_log "  slug: $PROJECT_SLUG"
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

kc_ensure_symlink "$KNOWLEDGE_REAL_DIR" "$KNOWLEDGE_POINTER_PATH" "agent-knowledge"
case "$KC_LAST_ACTION" in
    created|updated|would-create|would-update)
        CHANGES+=("pointer")
        ;;
esac

if [ ! -f "$AGENT_PROJECT_FILE" ] || [ "$FORCE" -eq 1 ]; then
    kc_replace_in_template \
        "$PROJECT_TEMPLATE_DIR/.agent-project.yaml" \
        "$AGENT_PROJECT_FILE" \
        ".agent-project.yaml" \
        "<project-name>" "$PROJECT_NAME" \
        "<project-slug>" "$PROJECT_SLUG" \
        "<path-to-agents-rules>" "$AGENTS_RULES_DIR" \
        "<absolute-path-to-dedicated-knowledge-folder>" "$KNOWLEDGE_REAL_DIR"
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
    kc_copy_file "$PROJECT_TEMPLATE_DIR/gitignore.agent-knowledge" "$TARGET_PROJECT/.gitignore" ".gitignore"
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
        kc_replace_in_template \
            "$HOOK_TEMPLATE" \
            "$CURSOR_HOOKS_FILE" \
            ".cursor/hooks.json" \
            "<path-to-agents-rules>" "$AGENTS_RULES_DIR" \
            "<repo-path>" "$TARGET_PROJECT"
        case "$KC_LAST_ACTION" in
            created|updated|would-create|would-update)
                CHANGES+=(".cursor/hooks.json")
                ;;
        esac
    else
        kc_log "  exists: .cursor/hooks.json (left unchanged)"
    fi
fi

if [ ! -f "$KNOWLEDGE_REAL_DIR/Memory/MEMORY.md" ] || [ ! -f "$KNOWLEDGE_REAL_DIR/STATUS.md" ] || [ "$FORCE" -eq 1 ]; then
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

if [ "$JSON_MODE" -ne 1 ]; then
    kc_log ""
    kc_log "Next steps:"
    kc_log "  1. Run scripts/doctor.sh $TARGET_PROJECT"
    kc_log "  2. Review $AGENT_PROJECT_FILE"
    if [ "$INSTALL_HOOKS" -eq 1 ]; then
        kc_log "  3. Review $CURSOR_HOOKS_FILE before enabling editor hooks"
    fi
fi
