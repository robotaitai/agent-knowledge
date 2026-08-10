#!/bin/bash
#
# Optional structural evidence sync for graph-style discovery outputs.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
. "$SCRIPT_DIR/lib/knowledge-common.sh"

usage() {
    cat <<'EOF'
Usage:
  scripts/graphify-sync.sh [project-dir]
  scripts/graphify-sync.sh --project <dir> [--source <path>] [--dry-run] [--json] [--summary-file <file>]
EOF
}

TARGET_PROJECT_ARG="."
SOURCE_OVERRIDE=""
POSITIONAL=()
SCANNED=()
IMPORTED=()
OUTPUTS_GENERATED=()
CACHED=()
SKIPPED=()
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
        --source)
            SOURCE_OVERRIDE="${2:-}"
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

GRAPHIFY_EVIDENCE_DIR="$EVIDENCE_IMPORTS_DIR/graphify"
GRAPHIFY_OUTPUTS_DIR="$OUTPUTS_DIR/graphify"

kc_ensure_dir "$GRAPHIFY_EVIDENCE_DIR" "bedrock/Evidence/imports/graphify"
kc_ensure_dir "$GRAPHIFY_OUTPUTS_DIR" "bedrock/Outputs/graphify"
kc_ensure_dir "$EVIDENCE_CACHE_DIR" "bedrock/Evidence/.cache"

normalize_source() {
    local path="$1"
    kc_resolve_relative "$TARGET_PROJECT" "$path"
}

project_relpath() {
    local abs="$1"
    case "$abs" in
        "$TARGET_PROJECT"/*)
            printf '%s\n' "${abs#$TARGET_PROJECT/}"
            ;;
        *)
            printf '%s\n' "$abs"
            ;;
    esac
}

safe_graphify_artifact() {
    local path="$1"
    case "$path" in
        *.json|*.md|*.txt|*.yaml|*.yml|*.csv|*.dot|*.mermaid|*.mmd)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

candidate_sources() {
    local candidate=""
    local normalized=""
    local rel=""

    if [ -n "$SOURCE_OVERRIDE" ]; then
        normalized="$(normalize_source "$SOURCE_OVERRIDE")"
        [ -e "$normalized" ] && printf '%s\n' "$normalized"
    fi

    if [ -n "${GRAPHIFY_EXPORT_DIR:-}" ]; then
        normalized="$(normalize_source "$GRAPHIFY_EXPORT_DIR")"
        [ -e "$normalized" ] && printf '%s\n' "$normalized"
    fi

    for candidate in \
        .graphify \
        graphify \
        graphify-output \
        graphify-report.json \
        graphify-report.md \
        graphify-report.txt \
        structural-graph.json \
        graph.json \
        graph/report.json \
        graph/report.md \
        graph/report.txt \
        codegraph.json \
        codegraph; do
        normalized="$TARGET_PROJECT/$candidate"
        [ -e "$normalized" ] || continue
        rel="$(project_relpath "$normalized")"
        if kc_path_is_ignored "$rel"; then
            SKIPPED+=("$rel")
            continue
        fi
        printf '%s\n' "$normalized"
    done
}

import_graph_artifact() {
    local src="$1"
    local rel_src="$2"
    local dst="$GRAPHIFY_EVIDENCE_DIR/$rel_src"
    local meta_dst="$dst.meta.json"
    local signature=""
    local changed=0

    signature="$(kc_signature_from_paths "$src")"
    if kc_cache_is_current "graphify-import" "$rel_src" "$signature" "$dst" "$meta_dst"; then
        CACHED+=("bedrock/Evidence/imports/graphify/$rel_src")
        return 0
    fi

    kc_copy_file "$src" "$dst" "bedrock/Evidence/imports/graphify/$rel_src"
    case "$KC_LAST_ACTION" in
        created|updated|would-create|would-update)
            changed=1
            ;;
    esac

    kc_write_metadata_json "$meta_dst" "bedrock/Evidence/imports/graphify/$rel_src.meta.json" "$rel_src" "graph-artifact" "EXTRACTED" "$GENERATED_AT" "$rel_src" "Imported machine-generated structural artifact. Review before promoting any claim into Memory."
    case "$KC_LAST_ACTION" in
        created|updated|would-create|would-update)
            changed=1
            ;;
    esac

    kc_cache_store "graphify-import" "$rel_src" "$signature"

    if [ "$changed" -eq 1 ]; then
        IMPORTED+=("bedrock/Evidence/imports/graphify/$rel_src")
    fi
}

capture_graphify_note() {
    local key="$1"
    local dst="$2"
    local label="$3"
    local bucket="$4"
    local signature="$5"
    local changed=0
    local tmp_file

    if kc_cache_is_current "graphify-note" "$key" "$signature" "$dst"; then
        CACHED+=("$label")
        return 0
    fi

    tmp_file="$(mktemp)"
    cat > "$tmp_file"
    kc_apply_temp_file "$tmp_file" "$dst" "$label"
    case "$KC_LAST_ACTION" in
        created|updated|would-create|would-update)
            changed=1
            ;;
    esac
    kc_cache_store "graphify-note" "$key" "$signature"
    if [ "$changed" -eq 1 ]; then
        case "$bucket" in
            imports)
                IMPORTED+=("$label")
                ;;
            outputs)
                OUTPUTS_GENERATED+=("$label")
                ;;
        esac
    fi
}

GRAPHIFY_AVAILABLE=0
if command -v graphify >/dev/null 2>&1; then
    GRAPHIFY_AVAILABLE=1
fi

SOURCE_CANDIDATES="$(candidate_sources | awk 'NF && !seen[$0]++ { print $0 }')"
if [ -z "$SOURCE_CANDIDATES" ]; then
    if [ "$GRAPHIFY_AVAILABLE" -eq 1 ]; then
        WARNINGS+=("graphify is available but no export artifacts or source override were found")
    else
        WARNINGS+=("graphify artifacts were not found and graphify is not installed")
    fi
else
    while IFS= read -r source_path; do
        [ -n "$source_path" ] || continue
        SCANNED+=("$source_path")
        if [ -d "$source_path" ]; then
            while IFS= read -r artifact; do
                [ -n "$artifact" ] || continue
                if ! safe_graphify_artifact "$artifact"; then
                    SKIPPED+=("$(project_relpath "$artifact")")
                    continue
                fi
                rel_artifact="$(project_relpath "$artifact")"
                case "$artifact" in
                    "$TARGET_PROJECT"/*)
                        if kc_path_is_ignored "$rel_artifact"; then
                            SKIPPED+=("$rel_artifact")
                            continue
                        fi
                        rel_import="${rel_artifact#$(project_relpath "$source_path")/}"
                        ;;
                    *)
                        rel_import="${artifact#$source_path/}"
                        ;;
                esac
                import_graph_artifact "$artifact" "$rel_import"
            done <<EOF
$(find "$source_path" -type f 2>/dev/null | sort)
EOF
        else
            if ! safe_graphify_artifact "$source_path"; then
                SKIPPED+=("$(project_relpath "$source_path")")
                continue
            fi
            import_graph_artifact "$source_path" "$(basename "$source_path")"
        fi
    done <<EOF
$SOURCE_CANDIDATES
EOF
fi

IMPORTED_LIST="$(printf '%s\n' "${IMPORTED[@]+"${IMPORTED[@]}"}" | awk 'NF')"
SKIPPED_LIST="$(printf '%s\n' "${SKIPPED[@]+"${SKIPPED[@]}"}" | awk 'NF')"
SUMMARY_SIGNATURE="$(kc_signature_from_lines "$(printf '%s\n---\n%s\n---\n%s\n---\n%s\n' "$SOURCE_CANDIDATES" "$IMPORTED_LIST" "$GRAPHIFY_AVAILABLE" "$SKIPPED_LIST")")"
capture_graphify_note "evidence-summary" "$GRAPHIFY_EVIDENCE_DIR/SUMMARY.md" "bedrock/Evidence/imports/graphify/SUMMARY.md" "imports" "$SUMMARY_SIGNATURE" <<EOF
---
note_type: structural-evidence
project: $PROJECT_NAME
profile: ${PROJECT_PROFILE:-unknown}
source: graphify-sync.sh
kind: graphify-summary
confidence: EXTRACTED
generated_at: $GENERATED_AT
related_paths:
$(kc_yaml_list "$(printf '%s\n' "$SOURCE_CANDIDATES" | while IFS= read -r p; do [ -n "$p" ] || continue; project_relpath "$p"; done)" 2)
notes:
  - Optional machine-generated structural imports.
  - Evidence only. Do not promote automatically into Memory.
tags:
  - bedrock
  - evidence
  - graphify
---

# Graphify Evidence Summary

## Purpose

- Index optional machine-generated structure imports for later review.

## Current State

- Graphify command available: \`$(if [ "$GRAPHIFY_AVAILABLE" -eq 1 ]; then echo yes; else echo no; fi)\`
- Imported artifacts: \`$(printf '%s\n' "$IMPORTED_LIST" | awk 'NF { count++ } END { print count + 0 }')\`
- Cached artifacts: \`$(printf '%s\n' "${CACHED[@]+"${CACHED[@]}"}" | awk 'NF { count++ } END { print count + 0 }')\`

## Imported Files

$(if [ -n "$IMPORTED_LIST" ]; then printf '%s\n' "$IMPORTED_LIST" | awk 'NF { sub(/^bedrock/Evidence/imports/graphify//, "", $0); printf "- [%s](%s)\n", $0, $0 }'; else echo "- None."; fi)

## Promotion Rule

- Graph exports are structural evidence first.
- Promote a claim into \`Memory/\` only after agent review confirms it is durable and useful.
EOF

capture_graphify_note "output-summary" "$GRAPHIFY_OUTPUTS_DIR/structural-summary.md" "bedrock/Outputs/graphify/structural-summary.md" "outputs" "$SUMMARY_SIGNATURE" <<EOF
---
note_type: generated-output
project: $PROJECT_NAME
profile: ${PROJECT_PROFILE:-unknown}
source: Evidence/imports/graphify/SUMMARY.md
kind: graphify-structural-summary
confidence: INFERRED
generated_at: $GENERATED_AT
related_paths:
$(kc_yaml_list "$(printf '%s\n' "$SOURCE_CANDIDATES" | while IFS= read -r p; do [ -n "$p" ] || continue; project_relpath "$p"; done)" 2)
notes:
  - Derived from optional graph/discovery artifacts.
  - Output only. Do not treat as durable memory without review.
tags:
  - bedrock
  - outputs
  - graphify
---

# Graphify Structural Summary

## Purpose

- Fast orientation note for optional graph-style discovery imports.

## Current Signal

- Graphify command available: \`$(if [ "$GRAPHIFY_AVAILABLE" -eq 1 ]; then echo yes; else echo no; fi)\`
- Source candidates scanned: \`$(printf '%s\n' "$SOURCE_CANDIDATES" | awk 'NF { count++ } END { print count + 0 }')\`
- Imported artifacts: \`$(printf '%s\n' "$IMPORTED_LIST" | awk 'NF { count++ } END { print count + 0 }')\`

## Evidence Location

- [../../Evidence/imports/graphify/SUMMARY.md](../../Evidence/imports/graphify/SUMMARY.md)

## Promotion Rule

- Keep graph outputs in \`Evidence/\` or \`Outputs/\` by default.
- Promote only curated, durable conclusions into \`Memory/\`.
EOF

kc_status_load
if [ "${DRY_RUN:-0}" -eq 0 ] && { [ ${#IMPORTED[@]} -gt 0 ] || [ ${#OUTPUTS_GENERATED[@]} -gt 0 ]; }; then
    STATUS_LAST_GRAPH_SYNC="$(kc_now_utc)"
fi
STATUS_WARNING_LINES="$(printf '%s\n' "${WARNINGS[@]+"${WARNINGS[@]}"}")"
kc_status_write "$STATUS_WARNING_LINES"

json_summary="{"
json_summary="$json_summary\"script\":\"graphify-sync\","
json_summary="$json_summary\"project_root\":\"$(kc_json_escape "$TARGET_PROJECT")\","
json_summary="$json_summary\"dry_run\":$(kc_json_bool "$DRY_RUN"),"
json_summary="$json_summary\"graphify_available\":$(kc_json_bool "$GRAPHIFY_AVAILABLE"),"
json_summary="$json_summary\"scanned\":$(kc_json_array "${SCANNED[@]+"${SCANNED[@]}"}"),"
json_summary="$json_summary\"imported\":$(kc_json_array "${IMPORTED[@]+"${IMPORTED[@]}"}"),"
json_summary="$json_summary\"outputs\":$(kc_json_array "${OUTPUTS_GENERATED[@]+"${OUTPUTS_GENERATED[@]}"}"),"
json_summary="$json_summary\"cached\":$(kc_json_array "${CACHED[@]+"${CACHED[@]}"}"),"
json_summary="$json_summary\"skipped\":$(kc_json_array "${SKIPPED[@]+"${SKIPPED[@]}"}"),"
json_summary="$json_summary\"warnings\":$(kc_json_array "${WARNINGS[@]+"${WARNINGS[@]}"}")"
json_summary="$json_summary}"
kc_write_json_output "$json_summary"

if [ "$JSON_MODE" -ne 1 ]; then
    kc_log "Graphify sync: $TARGET_PROJECT"
    if [ ${#SCANNED[@]} -gt 0 ]; then
        kc_log "Scanned:"
        printf '  %s\n' "${SCANNED[@]+"${SCANNED[@]}"}"
    fi
    if [ ${#IMPORTED[@]} -gt 0 ]; then
        kc_log ""
        kc_log "Imported:"
        printf '  %s\n' "${IMPORTED[@]+"${IMPORTED[@]}"}"
    fi
    if [ ${#CACHED[@]} -gt 0 ]; then
        kc_log ""
        kc_log "Cached:"
        printf '  %s\n' "${CACHED[@]+"${CACHED[@]}"}"
    fi
    if [ ${#WARNINGS[@]} -gt 0 ]; then
        kc_log ""
        kc_log "Warnings:"
        printf '  %s\n' "${WARNINGS[@]+"${WARNINGS[@]}"}"
    fi
fi
