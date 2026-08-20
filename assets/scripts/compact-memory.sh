#!/bin/bash
#
# Compact and clean memory notes conservatively.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
. "$SCRIPT_DIR/lib/knowledge-common.sh"

usage() {
    cat <<'EOF'
Usage:
  scripts/compact-memory.sh [project-dir]
  scripts/compact-memory.sh --project <dir> [--dry-run] [--json] [--summary-file <file>]
EOF
}

TARGET_PROJECT_ARG="."
POSITIONAL=()
COMPACTED=()
WARNINGS=()

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
[ -d "$MEMORY_DIR" ] || kc_fail "No memory tree at: $MEMORY_DIR"

compact_recent_changes() {
    local file="$1"
    local limit="$2"
    local label="$3"
    local tmp_file

    tmp_file="$(mktemp)"
    awk -v limit="$limit" '
        BEGIN {
            in_recent = 0
            count = 0
        }
        {
            if ($0 == "## Recent Changes") {
                in_recent = 1
                delete seen
                print
                next
            }

            if (in_recent && /^## /) {
                in_recent = 0
            }

            if (in_recent) {
                if ($0 ~ /^- /) {
                    if (!($0 in seen) && count < limit) {
                        seen[$0] = 1
                        kept[++count] = $0
                    }
                    next
                }
                if ($0 ~ /^[[:space:]]*$/) {
                    next
                }
            }

            print

            if (!in_recent) {
                next
            }
        }
        END {
            if (count > 0) {
                for (i = 1; i <= count; i++) {
                    print kept[i]
                }
            }
        }
    ' "$file" > "$tmp_file"

    kc_apply_temp_file "$tmp_file" "$file" "$label"
    case "$KC_LAST_ACTION" in
        updated|would-update)
            COMPACTED+=("$label")
            ;;
    esac
}

health_check_note() {
    local file="$1"
    local rel="$2"
    local lines

    lines="$(wc -l < "$file" 2>/dev/null || echo 0)"
    if [ "$lines" -gt 220 ]; then
        WARNINGS+=("$rel is still over 220 lines after compaction")
    elif [ "$lines" -gt 180 ]; then
        WARNINGS+=("$rel is still over 180 lines after compaction")
    fi
}

kc_log "Compacting memory: $MEMORY_DIR"

memory_files="$(find "$MEMORY_DIR" -name "*.md" | sort)"
while IFS= read -r file; do
    [ -n "$file" ] || continue
    rel="$(kc_rel_knowledge_path "$file")"
    limit=12
    case "$file" in
        "$MEMORY_ROOT")
            limit=8
            ;;
        */decisions/*)
            limit=8
            ;;
    esac
    compact_recent_changes "$file" "$limit" "$rel"
done <<EOF
$memory_files
EOF

while IFS= read -r file; do
    [ -n "$file" ] || continue
    rel="$(kc_rel_knowledge_path "$file")"
    health_check_note "$file" "$rel"
done <<EOF
$memory_files
EOF

# Prune old captures: keep the 30 most recent, remove the rest.
CAPTURES_DIR="$EVIDENCE_DIR/captures"
if [ -d "$CAPTURES_DIR" ]; then
    captures_all="$(find "$CAPTURES_DIR" -name "*.yaml" | sort -r)"
    capture_count=0
    pruned_count=0
    while IFS= read -r cap; do
        [ -n "$cap" ] || continue
        capture_count=$((capture_count + 1))
        if [ "$capture_count" -gt 30 ]; then
            if [ "${DRY_RUN:-0}" -eq 1 ]; then
                kc_log "  would prune capture: $(basename "$cap")"
            else
                rm -f "$cap"
                pruned_count=$((pruned_count + 1))
            fi
        fi
    done <<EOF
$captures_all
EOF
    if [ "$pruned_count" -gt 0 ]; then
        COMPACTED+=("Evidence/captures ($pruned_count removed)")
        kc_log "  pruned $pruned_count old capture files (kept 30)"
    fi
fi

kc_status_load
if [ "${DRY_RUN:-0}" -eq 0 ] && [ ${#COMPACTED[@]} -gt 0 ]; then
    STATUS_LAST_COMPACTION="$(kc_now_utc)"
fi
STATUS_WARNING_LINES="$(printf '%s\n' "${WARNINGS[@]+"${WARNINGS[@]}"}")"
kc_status_write "$STATUS_WARNING_LINES"

json_summary="{"
json_summary="$json_summary\"script\":\"compact-memory\","
json_summary="$json_summary\"project_root\":\"$(kc_json_escape "$TARGET_PROJECT")\","
json_summary="$json_summary\"dry_run\":$(kc_json_bool "$DRY_RUN"),"
json_summary="$json_summary\"compacted\":$(kc_json_array "${COMPACTED[@]+"${COMPACTED[@]}"}"),"
json_summary="$json_summary\"warnings\":$(kc_json_array "${WARNINGS[@]+"${WARNINGS[@]}"}")"
json_summary="$json_summary}"
kc_write_json_output "$json_summary"

if [ "$JSON_MODE" -ne 1 ]; then
    kc_log ""
    if [ ${#COMPACTED[@]} -gt 0 ]; then
        kc_log "Compacted notes:"
        printf '  %s\n' "${COMPACTED[@]+"${COMPACTED[@]}"}"
    else
        kc_log "No compaction changes were needed."
    fi

    if [ ${#WARNINGS[@]} -gt 0 ]; then
        kc_log ""
        kc_log "Warnings:"
        printf '  %s\n' "${WARNINGS[@]+"${WARNINGS[@]}"}"
    fi
fi
