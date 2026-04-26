#!/bin/bash
#
# Validate the project knowledge layout and key operational links.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENTS_RULES_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=/dev/null
. "$SCRIPT_DIR/lib/knowledge-common.sh"

usage() {
    cat <<'EOF'
Usage:
  scripts/validate-knowledge.sh [project-dir]
  scripts/validate-knowledge.sh --project <dir> [--dry-run] [--json] [--summary-file <file>]
EOF
}

TARGET_PROJECT_ARG="."
POSITIONAL=()
ERRORS=()
WARNINGS=()
CHECKS=()

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

if [ ${#POSITIONAL[@]} -ge 1 ]; then
    TARGET_PROJECT_ARG="${POSITIONAL[0]}"
fi

kc_load_project_context "$TARGET_PROJECT_ARG"

check_required_path() {
    local path="$1"
    local label="$2"
    if [ -e "$path" ]; then
        CHECKS+=("$label:ok")
    else
        ERRORS+=("Missing $label at $path")
    fi
}

check_required_dir() {
    local path="$1"
    local label="$2"
    if [ -d "$path" ]; then
        CHECKS+=("$label:ok")
    else
        ERRORS+=("Missing directory $label at $path")
    fi
}

check_required_path "$AGENT_PROJECT_FILE" ".agent-project.yaml"
check_required_dir "$KNOWLEDGE_POINTER_PATH" "agent-knowledge local handle"
check_required_dir "$KNOWLEDGE_REAL_DIR" "real knowledge dir"
check_required_path "$STATUS_FILE" "STATUS.md"
check_required_path "$MEMORY_ROOT" "Memory/MEMORY.md"
check_required_dir "$DECISIONS_DIR" "Memory/decisions"
check_required_dir "$EVIDENCE_RAW_DIR" "Evidence/raw"
check_required_dir "$EVIDENCE_IMPORTS_DIR" "Evidence/imports"
check_required_dir "$OUTPUTS_DIR" "Outputs"

if [ -f "$AGENT_PROJECT_FILE" ]; then
    for key in name slug pointer_path real_path memory_root evidence_raw evidence_imports; do
        if [ -z "$(kc_yaml_leaf_value "$AGENT_PROJECT_FILE" "$key" || true)" ]; then
            ERRORS+=("Missing required .agent-project.yaml key: $key")
        fi
    done
fi

pointer_resolved="$(kc_pointer_resolved_path || true)"
if [ -z "$pointer_resolved" ]; then
    ERRORS+=("Unable to resolve ./agent-knowledge as a local handle.")
elif [ "${VAULT_MODE:-external}" = "local" ]; then
    # In local mode agent-knowledge/ is a real directory inside the repo -- OK
    if [ -L "$KNOWLEDGE_POINTER_PATH" ]; then
        WARNINGS+=("vault_mode is 'local' but agent-knowledge is still a symlink. Run: agent-knowledge migrate-to-local")
    fi
elif [ "$pointer_resolved" != "$KNOWLEDGE_REAL_DIR" ]; then
    ERRORS+=("agent-knowledge resolves to $pointer_resolved but .agent-project.yaml expects $KNOWLEDGE_REAL_DIR")
elif [ ! -L "$KNOWLEDGE_POINTER_PATH" ]; then
    if kc_is_windows_like; then
        WARNINGS+=("agent-knowledge is not reported as a symlink; if this is a junction, verify it still points to the external knowledge folder.")
    else
        ERRORS+=("agent-knowledge must be a symlink to the external knowledge folder in canonical mode. Run: agent-knowledge migrate-to-local to switch to local mode.")
    fi
fi

validate_durable_note() {
    local file="$1"
    local rel
    rel="$(kc_rel_knowledge_path "$file")"
    local note_type

    note_type="$(kc_yaml_leaf_value "$file" "note_type" || true)"
    if ! kc_has_frontmatter "$file"; then
        ERRORS+=("$rel is missing YAML frontmatter")
        return
    fi

    case "$note_type" in
        durable-memory-root|durable-memory-branch|memory-branch|tooling-memory|tooling-index)
            for heading in "## Purpose" "## Current State" "## Recent Changes" "## Decisions" "## Open Questions"; do
                if ! grep -q "^$heading\$" "$file"; then
                    ERRORS+=("$rel is missing required section: $heading")
                fi
            done
            ;;
        structural-evidence|generated-output)
            for heading in "## Purpose"; do
                if ! grep -q "^$heading\$" "$file"; then
                    ERRORS+=("$rel is missing required section: $heading")
                fi
            done
            ;;
        decision)
            for heading in "## What" "## Why" "## Alternatives Considered" "## Consequences"; do
                if ! grep -q "^$heading\$" "$file"; then
                    ERRORS+=("$rel is missing required section: $heading")
                fi
            done
            ;;
    esac
}

check_links() {
    local file="$1"
    local rel
    rel="$(kc_rel_knowledge_path "$file")"
    local link=""
    local target=""
    local base_dir
    base_dir="$(dirname "$file")"

    while IFS= read -r link; do
        target="$(printf '%s' "$link" | sed 's/^[^)]*(//; s/)$//')"
        case "$target" in
            http:*|https:*|mailto:*|'#'*|'')
                continue
                ;;
        esac
        if [ ! -e "$base_dir/$target" ]; then
            WARNINGS+=("Broken-looking link in $rel -> $target")
        fi
    done <<EOF
$(grep -o '\[[^]]*\]([^)]*)' "$file" 2>/dev/null || true)
EOF
}

memory_files="$(find "$MEMORY_DIR" -name "*.md" | sort)"
while IFS= read -r file; do
    [ -n "$file" ] || continue
    validate_durable_note "$file"
done <<EOF
$memory_files
EOF

# Check same-name branch convention: folders under Memory/ should have a same-name entry note
branch_dirs="$(find "$MEMORY_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort)"
while IFS= read -r branch_dir; do
    [ -n "$branch_dir" ] || continue
    branch_name="$(basename "$branch_dir")"
    entry_note="$branch_dir/$branch_name.md"
    if [ ! -f "$entry_note" ]; then
        WARNINGS+=("Branch folder Memory/$branch_name/ is missing its entry note: $branch_name.md")
    fi
done <<EOF
$branch_dirs
EOF

knowledge_markdown="$(find "$KNOWLEDGE_DIR" -name "*.md" | sort)"
while IFS= read -r file; do
    [ -n "$file" ] || continue
    check_links "$file"
done <<EOF
$knowledge_markdown
EOF

for path in \
    "$AGENTS_RULES_DIR/scripts/update-knowledge.sh" \
    "$AGENTS_RULES_DIR/scripts/ship.sh" \
    "$AGENTS_RULES_DIR/scripts/global-knowledge-sync.sh" \
    "$AGENTS_RULES_DIR/scripts/graphify-sync.sh" \
    "$AGENTS_RULES_DIR/scripts/bootstrap-memory-tree.sh" \
    "$AGENTS_RULES_DIR/scripts/import-agent-history.sh" \
    "$AGENTS_RULES_DIR/scripts/compact-memory.sh" \
    "$AGENTS_RULES_DIR/scripts/validate-knowledge.sh" \
    "$AGENTS_RULES_DIR/scripts/doctor.sh" \
    "$AGENTS_RULES_DIR/commands/knowledge-sync.md" \
    "$AGENTS_RULES_DIR/commands/ship.md" \
    "$AGENTS_RULES_DIR/commands/global-knowledge-sync.md" \
    "$AGENTS_RULES_DIR/commands/graphify-sync.md" \
    "$AGENTS_RULES_DIR/commands/doctor.md" \
    "$AGENTS_RULES_DIR/rules/memory-bootstrap.mdc" \
    "$AGENTS_RULES_DIR/rules/memory-writeback.mdc" \
    "$AGENTS_RULES_DIR/rules/history-backfill.mdc" \
    "$AGENTS_RULES_DIR/rules/workflow-orchestration.mdc"; do
    [ -e "$path" ] || ERRORS+=("Missing required framework target: $path")
done

result="ok"
exit_code=0
if [ ${#ERRORS[@]} -gt 0 ]; then
    result="error"
    exit_code=1
elif [ ${#WARNINGS[@]} -gt 0 ]; then
    result="warn"
fi

kc_status_load
if [ "${DRY_RUN:-0}" -eq 0 ]; then
    STATUS_LAST_VALIDATION="$(kc_now_utc)"
    STATUS_LAST_VALIDATION_RESULT="$result"
fi
STATUS_WARNING_LINES="$(printf '%s\n' "${WARNINGS[@]+"${WARNINGS[@]}"}")"
kc_status_write "$STATUS_WARNING_LINES"

json_summary="{"
json_summary="$json_summary\"script\":\"validate-knowledge\","
json_summary="$json_summary\"project_root\":\"$(kc_json_escape "$TARGET_PROJECT")\","
json_summary="$json_summary\"result\":\"$(kc_json_escape "$result")\","
json_summary="$json_summary\"dry_run\":$(kc_json_bool "$DRY_RUN"),"
json_summary="$json_summary\"errors\":$(kc_json_array "${ERRORS[@]+"${ERRORS[@]}"}"),"
json_summary="$json_summary\"warnings\":$(kc_json_array "${WARNINGS[@]+"${WARNINGS[@]}"}"),"
json_summary="$json_summary\"checks\":$(kc_json_array "${CHECKS[@]+"${CHECKS[@]}"}")"
json_summary="$json_summary}"
kc_write_json_output "$json_summary"

if [ "$JSON_MODE" -ne 1 ]; then
    kc_log "Knowledge validation: $result"
    if [ ${#ERRORS[@]} -gt 0 ]; then
        kc_log "Errors:"
        printf '  %s\n' "${ERRORS[@]+"${ERRORS[@]}"}"
    fi
    if [ ${#WARNINGS[@]} -gt 0 ]; then
        kc_log "Warnings:"
        printf '  %s\n' "${WARNINGS[@]+"${WARNINGS[@]}"}"
    fi
fi

exit "$exit_code"
