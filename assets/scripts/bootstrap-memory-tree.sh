#!/bin/bash
#
# Bootstrap a minimal project cockpit under ./bedrock/.
#
# Usage:
#   ./bootstrap-memory-tree.sh [project-dir] [profile]
#   ./bootstrap-memory-tree.sh .                 # auto-detect profile hint
#   ./bootstrap-memory-tree.sh /path/to/project robotics
#
# Profile hints: web-app | robotics | ml-platform | hybrid
#
# What it does:
#   1. Detects a profile hint from manifests, docs, configs, tests, and workflows
#   2. Creates the minimal project cockpit: Memory/, Work/, Views/
#   3. Creates Memory/PROJECT.md, Memory/decisions.md, Memory/glossary.md, and Work/*.md
#   4. Stores profile hint in STATUS.md (the agent infers the actual ontology)
#
# What it does NOT do:
#   - Create per-area branch notes (the agent does this after inspecting the repo)
#   - Define the ontology tree (the agent infers it from the project)
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENTS_RULES_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=/dev/null
. "$SCRIPT_DIR/lib/knowledge-common.sh"
TEMPLATES_DIR="$AGENTS_RULES_DIR/templates/memory"
PROJECT_TEMPLATE_DIR="$AGENTS_RULES_DIR/templates/project/bedrock"
STATUS_TEMPLATE="$AGENTS_RULES_DIR/templates/project/bedrock/STATUS.md"

TARGET_PROJECT_ARG="."
PROFILE=""
POSITIONAL=()
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
        --project)
            TARGET_PROJECT_ARG="${2:-.}"
            shift 2
            ;;
        --profile)
            PROFILE="${2:-}"
            shift 2
            ;;
        *)
            POSITIONAL+=("$1")
            shift
            ;;
    esac
done

if [ "$SHOW_HELP" -eq 1 ]; then
    cat <<'EOF'
Usage:
  scripts/bootstrap-memory-tree.sh [project-dir] [profile]
  scripts/bootstrap-memory-tree.sh --project <dir> [--profile <profile>] [--dry-run] [--json] [--summary-file <file>] [--force]
EOF
    exit 0
fi

if [ ${#POSITIONAL[@]} -ge 1 ]; then
    TARGET_PROJECT_ARG="${POSITIONAL[0]}"
fi
if [ ${#POSITIONAL[@]} -ge 2 ] && [ -z "$PROFILE" ]; then
    PROFILE="${POSITIONAL[1]}"
fi

kc_load_project_context "$TARGET_PROJECT_ARG"
DATE="$(kc_today)"

{ [ -L "$KNOWLEDGE_POINTER_PATH" ] || [ "${VAULT_MODE:-}" = "local" ] || kc_is_windows_like; } || \
    kc_fail "Bootstrap requires ./bedrock to already be a pointer to the external knowledge folder. Run: bedrock init"

# ---------------------------------------------------------------------------
# Profile detection (hint only -- does not drive file creation)
# ---------------------------------------------------------------------------

detect_profile() {
    local dir="$1"
    local docs_text=""
    local has_workspace="no"
    local manifest_total=0

    local manifest_paths=""
    manifest_paths="$(list_existing_paths "$dir" \
        package.json pnpm-workspace.yaml nx.json turbo.json yarn.lock pnpm-lock.yaml package-lock.json \
        pyproject.toml requirements.txt setup.py setup.cfg Pipfile poetry.lock \
        Cargo.toml Cargo.lock go.mod go.sum CMakeLists.txt Makefile package.xml)"

    manifest_total="$(printf "%s\n" "$manifest_paths" | awk 'NF{count++} END{print count+0}')"

    if [ -f "$dir/pnpm-workspace.yaml" ] || [ -f "$dir/nx.json" ] || [ -f "$dir/turbo.json" ] || \
       [ -d "$dir/packages" ] || [ -d "$dir/services" ] || [ -d "$dir/apps" ] || \
       ( [ -f "$dir/package.json" ] && grep -q '"workspaces"' "$dir/package.json" 2>/dev/null ); then
        has_workspace="yes"
    fi

    docs_text="$(cat "$dir/README.md" "$dir/docs/README.md" "$dir/AGENTS.md" "$dir/CLAUDE.md" 2>/dev/null || true)"

    if [ -f "$dir/package.xml" ] || [ -f "$dir/CMakeLists.txt" ] || [ -d "$dir/urdf" ] || [ -d "$dir/launch" ] || \
       printf "%s" "$docs_text" | grep -Eiq 'ros2|ros |gazebo|rviz|urdf|moveit'; then
        echo "robotics"
        return
    fi

    if { [ -f "$dir/pyproject.toml" ] || [ -f "$dir/requirements.txt" ]; } && \
       { [ -d "$dir/notebooks" ] || [ -d "$dir/models" ] || [ -d "$dir/data" ] || \
         grep -Eiq 'torch|tensorflow|jax|sklearn|transformers|mlflow|wandb|ray' "$dir/requirements.txt" "$dir/pyproject.toml" 2>/dev/null || \
         printf "%s" "$docs_text" | grep -Eiq 'training|inference|model registry|feature store'; }; then
        echo "ml-platform"
        return
    fi

    if [ "$has_workspace" = "yes" ] || [ "$manifest_total" -ge 3 ]; then
        echo "hybrid"
        return
    fi

    if [ -f "$dir/package.json" ] && \
       grep -qE '"react"|"next"|"vue"|"svelte"|"angular"|"nuxt"|"vite"' "$dir/package.json" 2>/dev/null; then
        echo "web-app"
        return
    fi

    echo "hybrid"
}

relative_path() {
    sed "s|$TARGET_PROJECT/||" | sed "s|^$TARGET_PROJECT$|.|"
}

list_existing_paths() {
    local base="$1"
    shift
    local path=""

    for path in "$@"; do
        if [ -e "$base/$path" ]; then
            printf "%s\n" "$path"
        fi
    done
}

render_text_template() {
    local src="$1"
    local dst="$2"
    local current_state_lines="${3:-}"
    local recent_change_lines="${4:-}"
    local decision_lines="${5:-}"
    local open_question_lines="${6:-}"
    local branch_lines="${7:-}"
    local tmp_file

    tmp_file="$(mktemp)"

    TEMPLATE_PROJECT_NAME="$PROJECT_NAME" \
    TEMPLATE_DATE="$DATE" \
    TEMPLATE_CURRENT_STATE_LINES="$current_state_lines" \
    TEMPLATE_RECENT_CHANGE_LINES="$recent_change_lines" \
    TEMPLATE_DECISION_LINES="$decision_lines" \
    TEMPLATE_OPEN_QUESTION_LINES="$open_question_lines" \
    TEMPLATE_BRANCH_LINES="$branch_lines" \
    awk '
        BEGIN {
            project = ENVIRON["TEMPLATE_PROJECT_NAME"]
            date = ENVIRON["TEMPLATE_DATE"]
            current_state_lines = ENVIRON["TEMPLATE_CURRENT_STATE_LINES"]
            recent_change_lines = ENVIRON["TEMPLATE_RECENT_CHANGE_LINES"]
            decision_lines = ENVIRON["TEMPLATE_DECISION_LINES"]
            open_question_lines = ENVIRON["TEMPLATE_OPEN_QUESTION_LINES"]
            branch_lines = ENVIRON["TEMPLATE_BRANCH_LINES"]
        }
        {
            gsub(/<project-name>/, project)
            gsub(/<date>/, date)

            if ($0 == "<current-state-lines>") { print current_state_lines; next }
            if ($0 == "<recent-change-lines>") { print recent_change_lines; next }
            if ($0 == "<decision-lines>") { print decision_lines; next }
            if ($0 == "<open-question-lines>") { print open_question_lines; next }
            if ($0 == "<branch-lines>") { print branch_lines; next }

            print
        }' "$src" > "$tmp_file"

    kc_apply_temp_file "$tmp_file" "$dst" "$dst"
}

copy_static_template() {
    local src="$1"
    local dst="$2"
    local label="$3"

    render_text_template "$src" "$dst"
    case "$KC_LAST_ACTION" in
        created|updated|would-create|would-update)
            CHANGES+=("$label")
            ;;
    esac
}

render_dashboard_note() {
    local src="$1"
    local dst="$2"
    local label="$3"

    render_text_template "$src" "$dst"
    case "$KC_LAST_ACTION" in
        created|updated|would-create|would-update)
            CHANGES+=("$label")
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Detect or accept profile hint
# ---------------------------------------------------------------------------

if [ -z "$PROFILE" ]; then
    PROFILE="$(detect_profile "$TARGET_PROJECT")"
    kc_log "Auto-detected profile hint: $PROFILE"
fi

PROFILE_FILE="$TEMPLATES_DIR/profile.$PROFILE.yaml"
if [ ! -f "$PROFILE_FILE" ]; then
    kc_log "Warning: Unknown profile hint '$PROFILE'; defaulting to hybrid"
    PROFILE="hybrid"
    PROFILE_FILE="$TEMPLATES_DIR/profile.$PROFILE.yaml"
fi

if [ -f "$AGENT_PROJECT_FILE" ]; then
    tmp_file="$(mktemp)"
    sed "s/^\([[:space:]]*profile_hint:[[:space:]]*\).*/\1$PROFILE/" "$AGENT_PROJECT_FILE" > "$tmp_file"
    # Also handle legacy 'profile:' key for compat
    sed -i "s/^\([[:space:]]*profile:[[:space:]]*\).*/\1$PROFILE/" "$tmp_file" 2>/dev/null || true
    kc_apply_temp_file "$tmp_file" "$AGENT_PROJECT_FILE" ".agent-project.yaml"
    case "$KC_LAST_ACTION" in
        created|updated|would-create|would-update)
            CHANGES+=(".agent-project.yaml")
            ;;
    esac
fi

kc_log "Bootstrapping memory tree: $PROJECT_NAME (profile hint: $PROFILE)"
kc_log ""

# ---------------------------------------------------------------------------
# Create minimal directory scaffold
# ---------------------------------------------------------------------------

for dir in \
    "$KNOWLEDGE_DIR" \
    "$MEMORY_DIR" \
    "$WORK_DIR" \
    "$VIEWS_DIR" \
    "$VIEWS_SITE_DIR" \
    "$VIEWS_GRAPH_DIR"; do
    kc_ensure_dir "$dir" "$dir"
done

# ---------------------------------------------------------------------------
# Copy static templates
# ---------------------------------------------------------------------------

copy_static_template "$PROJECT_TEMPLATE_DIR/Memory/PROJECT.md" "$MEMORY_DIR/PROJECT.md" "bedrock/Memory/PROJECT.md"
copy_static_template "$PROJECT_TEMPLATE_DIR/Memory/decisions.md" "$MEMORY_DIR/decisions.md" "bedrock/Memory/decisions.md"
copy_static_template "$PROJECT_TEMPLATE_DIR/Memory/glossary.md" "$MEMORY_DIR/glossary.md" "bedrock/Memory/glossary.md"
copy_static_template "$PROJECT_TEMPLATE_DIR/Work/NOW.md" "$WORK_DIR/NOW.md" "bedrock/Work/NOW.md"
copy_static_template "$PROJECT_TEMPLATE_DIR/Work/backlog.md" "$WORK_DIR/backlog.md" "bedrock/Work/backlog.md"
copy_static_template "$PROJECT_TEMPLATE_DIR/Work/open-questions.md" "$WORK_DIR/open-questions.md" "bedrock/Work/open-questions.md"
copy_static_template "$PROJECT_TEMPLATE_DIR/Work/risks.md" "$WORK_DIR/risks.md" "bedrock/Work/risks.md"

# ---------------------------------------------------------------------------
# STATUS.md
# ---------------------------------------------------------------------------

# Local vaults record ./bedrock so the tracked STATUS.md is machine-independent.
STATUS_REAL_PATH_VALUE="$KNOWLEDGE_REAL_DIR"
[ "${VAULT_MODE:-external}" = "local" ] && STATUS_REAL_PATH_VALUE="./bedrock"

kc_replace_in_template \
    "$STATUS_TEMPLATE" \
    "$STATUS_FILE" \
    "bedrock/STATUS.md" \
    "<project-name>" "$PROJECT_NAME" \
    "<profile-type>" "$PROFILE" \
    "<absolute-path-to-dedicated-knowledge-folder>" "$STATUS_REAL_PATH_VALUE"
case "$KC_LAST_ACTION" in
    created|updated|would-create|would-update)
        CHANGES+=("bedrock/STATUS.md")
        ;;
esac

# ---------------------------------------------------------------------------
# STATUS bookkeeping
# ---------------------------------------------------------------------------

kc_status_load
STATUS_PROFILE="$PROFILE"
STATUS_REAL_PATH="$STATUS_REAL_PATH_VALUE"
STATUS_POINTER_PATH="$POINTER_DISPLAY"
if [ "${DRY_RUN:-0}" -eq 0 ] && [ ${#CHANGES[@]} -gt 0 ]; then
    STATUS_LAST_BOOTSTRAP="$(kc_now_utc)"
fi
kc_status_write

# ---------------------------------------------------------------------------
# JSON summary
# ---------------------------------------------------------------------------

json_summary="{"
json_summary="$json_summary\"script\":\"bootstrap-memory-tree\","
json_summary="$json_summary\"project_root\":\"$(kc_json_escape "$TARGET_PROJECT")\","
json_summary="$json_summary\"profile_hint\":\"$(kc_json_escape "$PROFILE")\","
json_summary="$json_summary\"real_knowledge_path\":\"$(kc_json_escape "$KNOWLEDGE_REAL_DIR")\","
json_summary="$json_summary\"dry_run\":$(kc_json_bool "$DRY_RUN"),"
json_summary="$json_summary\"changes\":$(kc_json_array "${CHANGES[@]+"${CHANGES[@]}"}")"
json_summary="$json_summary}"
kc_write_json_output "$json_summary"

if [ "$JSON_MODE" -ne 1 ]; then
    kc_log ""
    kc_log "Memory tree ready for: $PROJECT_NAME"
    kc_log "Profile hint: $PROFILE"
fi
