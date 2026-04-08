#!/bin/bash
#
# Quick troubleshooting entrypoint for the project knowledge system.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
. "$SCRIPT_DIR/lib/knowledge-common.sh"

usage() {
    cat <<'EOF'
Usage:
  scripts/doctor.sh [project-dir]
  scripts/doctor.sh --project <dir> [--json] [--summary-file <file>] [--dry-run]
EOF
}

TARGET_PROJECT_ARG="."
POSITIONAL=()
WARNINGS=()

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

validation_status="ok"
doctor_validate_args=(--project "$TARGET_PROJECT")
if [ "$DRY_RUN" -eq 1 ]; then
    doctor_validate_args+=(--dry-run)
fi
if ! kc_run_child_script "$SCRIPT_DIR/validate-knowledge.sh" "${doctor_validate_args[@]}"; then
    validation_status="error"
fi

if [ ! -d "$FRAMEWORK_REPO" ]; then
    WARNINGS+=("Framework repo path from .agent-project.yaml does not exist: $FRAMEWORK_REPO")
fi

if [ ! -f "$TARGET_PROJECT/AGENTS.md" ]; then
    WARNINGS+=("AGENTS.md is missing from the project repo.")
fi

if [ -f "$TARGET_PROJECT/.cursor/hooks.json" ]; then
    WARNINGS+=("Repo-local hooks are installed; review them if sync behavior is surprising.")
fi

if [ ! -L "$KNOWLEDGE_POINTER_PATH" ]; then
    if kc_is_windows_like; then
        WARNINGS+=("agent-knowledge is not reported as a symlink. If this is a junction, verify it still resolves to the external knowledge folder.")
    else
        WARNINGS+=("agent-knowledge is not a symlink. Canonical external source-of-truth mode is not active.")
    fi
fi

doctor_result="ok"
if [ "$validation_status" = "error" ]; then
    doctor_result="error"
elif [ ${#WARNINGS[@]} -gt 0 ]; then
    doctor_result="warn"
fi

kc_status_load
if [ "${DRY_RUN:-0}" -eq 0 ]; then
    STATUS_LAST_DOCTOR="$(kc_now_utc)"
    STATUS_LAST_DOCTOR_RESULT="$doctor_result"
fi
STATUS_WARNING_LINES="$(printf '%s\n' "${WARNINGS[@]+"${WARNINGS[@]}"}")"
kc_status_write "$STATUS_WARNING_LINES"

json_summary="{"
json_summary="$json_summary\"script\":\"doctor\","
json_summary="$json_summary\"project_root\":\"$(kc_json_escape "$TARGET_PROJECT")\","
json_summary="$json_summary\"result\":\"$(kc_json_escape "$doctor_result")\","
json_summary="$json_summary\"dry_run\":$(kc_json_bool "$DRY_RUN"),"
json_summary="$json_summary\"warnings\":$(kc_json_array "${WARNINGS[@]+"${WARNINGS[@]}"}")"
json_summary="$json_summary}"
kc_write_json_output "$json_summary"

if [ "$JSON_MODE" -ne 1 ]; then
    kc_log "Doctor result: $doctor_result"
    kc_log "  project: $TARGET_PROJECT"
    kc_log "  pointer: $KNOWLEDGE_POINTER_PATH"
    kc_log "  real knowledge path: $KNOWLEDGE_REAL_DIR"
    if [ ${#WARNINGS[@]} -gt 0 ]; then
        kc_log "Warnings:"
        printf '  %s\n' "${WARNINGS[@]+"${WARNINGS[@]}"}"
    fi
fi

if [ "$doctor_result" = "error" ]; then
    exit 1
fi
