#!/bin/bash
#
# Build or update a project-scoped tooling knowledge base from safe allowlisted sources.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
. "$SCRIPT_DIR/lib/knowledge-common.sh"

usage() {
    cat <<'EOF'
Usage:
  scripts/global-knowledge-sync.sh [project-dir]
  scripts/global-knowledge-sync.sh --project <dir> [--dry-run] [--json] [--summary-file <file>]
EOF
}

TARGET_PROJECT_ARG="."
POSITIONAL=()
SCANNED=()
SKIPPED=()
UPDATED=()
CACHED=()
WARNINGS=()
GENERATED_AT="$(kc_now_utc)"

while [ "$#" -gt 0 ]; do
    # Capture the status directly: after a failed `if` with no else branch, $?
    # is the status of the `if` itself (0), not of the condition -- which made
    # the two-argument return unreachable and silently swallowed --summary-file.
    flag_status=0
    kc_parse_common_flag "$@" || flag_status=$?
    if [ "$flag_status" -eq 0 ]; then
        shift
        continue
    fi
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
kc_require_knowledge_pointer

TOOLING_EVIDENCE_DIR="$EVIDENCE_TOOLING_DIR"
TOOLING_MEMORY_DIR="$MEMORY_DIR/tooling"
TOOLING_INDEX="$TOOLING_MEMORY_DIR/INDEX.md"

kc_ensure_dir "$TOOLING_EVIDENCE_DIR" "bedrock/Evidence/tooling"
kc_ensure_dir "$TOOLING_MEMORY_DIR" "bedrock/Memory/tooling"
kc_ensure_dir "$EVIDENCE_CACHE_DIR" "bedrock/Evidence/.cache"

is_allowlisted_tool_file() {
    local path="$1"
    case "$path" in
        "$HOME/.claude/settings.json"|"$HOME/.claude/CLAUDE.md"|"$HOME/.codex/config.toml"|"$HOME/.cursor/settings.json")
            return 0
            ;;
        "$HOME/.claude/agents/"*|"$HOME/.cursor/rules/"*|"$HOME/.cursor/snippets/"*)
            return 0
            ;;
    esac
    return 1
}

is_safe_tool_file() {
    local path="$1"
    case "$path" in
        *session*|*oauth*|*token*|*auth*|*cache*|*.db|*.sqlite|*.sqlite3)
            return 1
            ;;
        *)
            return 0
            ;;
    esac
}

redact_tool_file() {
    local src="$1"
    sed -E \
        -e 's/([Pp]assword[[:space:]]*[:=][[:space:]]*).*/\1[REDACTED]/g' \
        -e 's/([Tt]oken[[:space:]]*[:=][[:space:]]*).*/\1[REDACTED]/g' \
        -e 's/([Ss]ecret[[:space:]]*[:=][[:space:]]*).*/\1[REDACTED]/g' \
        -e 's/([Aa]uthorization[[:space:]]*[:=][[:space:]]*).*/\1[REDACTED]/g' \
        -e 's/([Cc]ookie[[:space:]]*[:=][[:space:]]*).*/\1[REDACTED]/g' \
        -e 's/([Oo]auth[^:=]*[[:space:]]*[:=][[:space:]]*).*/\1[REDACTED]/g' \
        -e 's/([Aa]pi[_-]?[Kk]ey[[:space:]]*[:=][[:space:]]*).*/\1[REDACTED]/g' \
        -e 's/([Rr]efresh[_-]?[Tt]oken[[:space:]]*[:=][[:space:]]*).*/\1[REDACTED]/g' \
        "$src"
}

capture_tooling_evidence() {
    local src="$1"
    local family="$2"
    local name="$3"
    local dst="$TOOLING_EVIDENCE_DIR/$name"
    local meta_dst="$dst.meta.json"
    local signature=""
    local tmp_file=""
    local changed=0

    signature="$(kc_signature_from_paths "$src")"
    if kc_cache_is_current "global-tooling" "$name" "$signature" "$dst" "$meta_dst"; then
        CACHED+=("bedrock/Evidence/tooling/$name")
        SCANNED+=("$src")
        TOOLING_FAMILIES="${TOOLING_FAMILIES}${family}"$'\n'
        TOOLING_FILES="${TOOLING_FILES}${family}|$name|$src"$'\n'
        return 0
    fi

    tmp_file="$(mktemp)"
    {
        printf '# Tooling Evidence\n'
        printf '# Source: %s\n' "$src"
        printf '# Kind: tooling-import\n'
        printf '# Confidence: EXTRACTED\n'
        printf '# Generated: %s\n\n' "$GENERATED_AT"
        redact_tool_file "$src"
    } > "$tmp_file"

    kc_apply_temp_file "$tmp_file" "$dst" "bedrock/Evidence/tooling/$name"
    case "$KC_LAST_ACTION" in
        created|updated|would-create|would-update)
            changed=1
            ;;
    esac

    kc_write_metadata_json "$meta_dst" "bedrock/Evidence/tooling/$name.meta.json" "$src" "tooling-import" "EXTRACTED" "$GENERATED_AT" "$src" "Redacted allowlisted tooling surface captured for project-scoped reference."
    case "$KC_LAST_ACTION" in
        created|updated|would-create|would-update)
            changed=1
            ;;
    esac

    kc_cache_store "global-tooling" "$name" "$signature"

    if [ "$changed" -eq 1 ]; then
        UPDATED+=("bedrock/Evidence/tooling/$name")
    fi
    SCANNED+=("$src")
    TOOLING_FAMILIES="${TOOLING_FAMILIES}${family}"$'\n'
    TOOLING_FILES="${TOOLING_FILES}${family}|$name|$src"$'\n'
}

write_tooling_note() {
    local family="$1"
    local title="$2"
    local purpose="$3"
    local file_name="$TOOLING_MEMORY_DIR/$family.md"
    local entries=""
    local line=""
    local signature=""
    local tmp_file=""

    while IFS= read -r line; do
        [ -n "$line" ] || continue
        case "$line" in
            "$family|"*)
                name="$(printf '%s' "$line" | cut -d'|' -f2)"
                src="$(printf '%s' "$line" | cut -d'|' -f3-)"
                entries="${entries}- [../../Evidence/tooling/$name](../../Evidence/tooling/$name) - Redacted import from \`$src\`."$'\n'
                ;;
        esac
    done <<EOF
$TOOLING_FILES
EOF

    [ -n "$entries" ] || entries="- No allowlisted sources were captured."
    signature="$(kc_signature_from_lines "$(printf '%s\n---\n%s\n---\n%s\n' "$family" "$title" "$entries")")"
    if kc_cache_is_current "global-tooling-note" "$family" "$signature" "$file_name"; then
        CACHED+=("bedrock/Memory/tooling/$family.md")
        return 0
    fi

    tmp_file="$(mktemp)"
    {
        printf '%s\n' '---'
        printf 'note_type: tooling-memory\n'
        printf 'project: %s\n' "$PROJECT_NAME"
        printf 'profile: %s\n' "$PROJECT_PROFILE"
        printf 'area: tooling-%s\n' "$family"
        printf 'status: active\n'
        printf 'last_updated: %s\n' "$(kc_today)"
        printf '%s\n\n' '---'
        printf '# %s\n\n' "$title"
        printf '## Purpose\n\n- %s\n\n' "$purpose"
        printf '## Current State\n\n- Tooling knowledge is derived only from allowlisted local configuration surfaces.\n- Sensitive lines are redacted before evidence is written.\n\n'
        printf '## Recent Changes\n\n- %s - Refreshed tooling evidence for `%s`.\n\n' "$(kc_today)" "$family"
        printf '## Decisions\n\n- No tooling-specific decisions recorded yet.\n\n'
        printf '## Open Questions\n\n- Which parts of this tooling setup are stable enough to rely on across sessions?\n\n'
        printf '## Subtopics\n\n%s\n' "$entries"
    } > "$tmp_file"

    kc_apply_temp_file "$tmp_file" "$file_name" "bedrock/Memory/tooling/$family.md"
    case "$KC_LAST_ACTION" in
        created|updated|would-create|would-update)
            UPDATED+=("bedrock/Memory/tooling/$family.md")
            ;;
    esac
    kc_cache_store "global-tooling-note" "$family" "$signature"
}

write_tooling_index() {
    local families=""
    local family=""
    local bullets=""
    local signature=""
    local tmp_file=""

    families="$(printf '%s\n' "$TOOLING_FAMILIES" | awk 'NF && !seen[$0]++ { print $0 }')"
    while IFS= read -r family; do
        [ -n "$family" ] || continue
        bullets="${bullets}- [${family}.md](${family}.md) - Redacted ${family} tooling summary."$'\n'
    done <<EOF
$families
EOF

    [ -n "$bullets" ] || bullets="- No allowlisted tooling sources were found."
    signature="$(kc_signature_from_lines "$bullets")"
    if kc_cache_is_current "global-tooling-note" "index" "$signature" "$TOOLING_INDEX"; then
        CACHED+=("bedrock/Memory/tooling/INDEX.md")
        return 0
    fi

    tmp_file="$(mktemp)"
    {
        printf '%s\n' '---'
        printf 'note_type: tooling-index\n'
        printf 'project: %s\n' "$PROJECT_NAME"
        printf 'status: active\n'
        printf 'last_updated: %s\n' "$(kc_today)"
        printf '%s\n\n' '---'
        printf '# Tooling\n\n'
        printf '## Purpose\n\n- Curated summary of safe local tooling surfaces relevant to this project.\n\n'
        printf '## Current State\n\n- Evidence is redacted and stored under [../../Evidence/tooling](../../Evidence/tooling).\n\n'
        printf '## Recent Changes\n\n- %s - Refreshed tooling knowledge from allowlisted local sources.\n\n' "$(kc_today)"
        printf '## Decisions\n\n- No tooling decisions recorded yet.\n\n'
        printf '## Open Questions\n\n- Which global tool defaults should be copied into project-specific durable memory?\n\n'
        printf '## Subtopics\n\n%s\n' "$bullets"
    } > "$tmp_file"

    kc_apply_temp_file "$tmp_file" "$TOOLING_INDEX" "bedrock/Memory/tooling/INDEX.md"
    case "$KC_LAST_ACTION" in
        created|updated|would-create|would-update)
            UPDATED+=("bedrock/Memory/tooling/INDEX.md")
            ;;
    esac
    kc_cache_store "global-tooling-note" "index" "$signature"
    kc_append_unique_bullet "$MEMORY_ROOT" "Subtopics" "- [Tooling](tooling/INDEX.md) - Redacted local tooling setup relevant to this project." "bedrock/Memory/MEMORY.md"
}

TOOLING_FAMILIES=""
TOOLING_FILES=""

for path in \
    "$HOME/.claude/settings.json" \
    "$HOME/.claude/CLAUDE.md" \
    "$HOME/.codex/config.toml" \
    "$HOME/.cursor/settings.json"; do
    if [ -f "$path" ] && is_allowlisted_tool_file "$path"; then
        if is_safe_tool_file "$path"; then
            case "$path" in
                "$HOME/.claude/"*)
                    capture_tooling_evidence "$path" "claude" "$(basename "$path" | tr '[:upper:]' '[:lower:]')"
                    ;;
                "$HOME/.codex/"*)
                    capture_tooling_evidence "$path" "codex" "$(basename "$path" | tr '[:upper:]' '[:lower:]')"
                    ;;
                "$HOME/.cursor/"*)
                    capture_tooling_evidence "$path" "cursor" "$(basename "$path" | tr '[:upper:]' '[:lower:]')"
                    ;;
            esac
        else
            SKIPPED+=("$path")
        fi
    fi
done

for dir in "$HOME/.claude/agents" "$HOME/.cursor/rules" "$HOME/.cursor/snippets"; do
    [ -d "$dir" ] || continue
    while IFS= read -r path; do
        [ -n "$path" ] || continue
        if ! is_allowlisted_tool_file "$path"; then
            continue
        fi
        if ! is_safe_tool_file "$path"; then
            SKIPPED+=("$path")
            continue
        fi
        case "$dir" in
            "$HOME/.claude/agents")
                capture_tooling_evidence "$path" "claude" "agents-$(basename "$path")"
                ;;
            "$HOME/.cursor/"*)
                capture_tooling_evidence "$path" "cursor" "$(basename "$dir")-$(basename "$path")"
                ;;
        esac
    done <<EOF
$(find "$dir" -type f \( -name "*.md" -o -name "*.json" -o -name "*.yaml" -o -name "*.yml" -o -name "*.toml" -o -name "*.txt" \) 2>/dev/null | sort)
EOF
done

if [ -z "$TOOLING_FILES" ]; then
    WARNINGS+=("No allowlisted local tooling sources were found.")
else
    if printf '%s\n' "$TOOLING_FAMILIES" | grep -q '^claude$'; then
        write_tooling_note "claude" "Claude Tooling" "Redacted Claude settings and prompt surfaces that may affect project work."
    fi
    if printf '%s\n' "$TOOLING_FAMILIES" | grep -q '^codex$'; then
        write_tooling_note "codex" "Codex Tooling" "Redacted Codex configuration surfaces that may affect project work."
    fi
    if printf '%s\n' "$TOOLING_FAMILIES" | grep -q '^cursor$'; then
        write_tooling_note "cursor" "Cursor Tooling" "Redacted Cursor customization surfaces that may affect project work."
    fi
    write_tooling_index
fi

kc_status_load
if [ "${DRY_RUN:-0}" -eq 0 ] && [ ${#UPDATED[@]} -gt 0 ]; then
    STATUS_LAST_GLOBAL_SYNC="$(kc_now_utc)"
fi
STATUS_WARNING_LINES="$(printf '%s\n' "${WARNINGS[@]+"${WARNINGS[@]}"}")"
kc_status_write "$STATUS_WARNING_LINES"

json_summary="{"
json_summary="$json_summary\"script\":\"global-knowledge-sync\","
json_summary="$json_summary\"project_root\":\"$(kc_json_escape "$TARGET_PROJECT")\","
json_summary="$json_summary\"dry_run\":$(kc_json_bool "$DRY_RUN"),"
json_summary="$json_summary\"scanned\":$(kc_json_array "${SCANNED[@]+"${SCANNED[@]}"}"),"
json_summary="$json_summary\"skipped\":$(kc_json_array "${SKIPPED[@]+"${SKIPPED[@]}"}"),"
json_summary="$json_summary\"updated\":$(kc_json_array "${UPDATED[@]+"${UPDATED[@]}"}"),"
json_summary="$json_summary\"cached\":$(kc_json_array "${CACHED[@]+"${CACHED[@]}"}"),"
json_summary="$json_summary\"warnings\":$(kc_json_array "${WARNINGS[@]+"${WARNINGS[@]}"}")"
json_summary="$json_summary}"
kc_write_json_output "$json_summary"

if [ "$JSON_MODE" -ne 1 ]; then
    kc_log "Global tooling sync: $TARGET_PROJECT"
    if [ ${#SCANNED[@]} -gt 0 ]; then
        kc_log "Scanned:"
        printf '  %s\n' "${SCANNED[@]+"${SCANNED[@]}"}"
    fi
    if [ ${#CACHED[@]} -gt 0 ]; then
        kc_log ""
        kc_log "Cached:"
        printf '  %s\n' "${CACHED[@]+"${CACHED[@]}"}"
    fi
    if [ ${#SKIPPED[@]} -gt 0 ]; then
        kc_log ""
        kc_log "Skipped for safety:"
        printf '  %s\n' "${SKIPPED[@]+"${SKIPPED[@]}"}"
    fi
fi
