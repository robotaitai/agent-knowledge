#!/bin/bash
#
# Project ship flow: validate, sync knowledge, commit, push, optionally open a PR.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
. "$SCRIPT_DIR/lib/knowledge-common.sh"

usage() {
    cat <<'EOF'
Usage:
  scripts/ship.sh [project-dir]
  scripts/ship.sh --project <dir> [--message <commit-message>] [--open-pr] [--open-pr=auto] [--dry-run] [--json] [--summary-file <file>]
EOF
}

TARGET_PROJECT_ARG="."
POSITIONAL=()
COMMIT_MESSAGE=""
OPEN_PR_MODE="no"
VALIDATION_LABELS=()
VALIDATION_RESULTS=()
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
        --message)
            COMMIT_MESSAGE="${2:-}"
            shift 2
            ;;
        --open-pr)
            OPEN_PR_MODE="yes"
            shift
            ;;
        --open-pr=auto)
            OPEN_PR_MODE="auto"
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

if [ ${#POSITIONAL[@]} -ge 1 ]; then
    TARGET_PROJECT_ARG="${POSITIONAL[0]}"
fi

kc_load_project_context "$TARGET_PROJECT_ARG"
kc_git_available || kc_fail "Ship requires a git repo."

branch="$(git -C "$TARGET_PROJECT" rev-parse --abbrev-ref HEAD)"
[ "$branch" != "HEAD" ] || kc_fail "Refusing to ship from a detached HEAD."

if [ -n "$(git -C "$TARGET_PROJECT" ls-files -u)" ]; then
    kc_fail "Refusing to ship with unresolved merge conflicts."
fi

detect_validation_commands() {
    if [ -f "$TARGET_PROJECT/Makefile" ] && grep -qE '^(test|check):' "$TARGET_PROJECT/Makefile" 2>/dev/null; then
        if grep -q '^test:' "$TARGET_PROJECT/Makefile" 2>/dev/null; then
            printf '%s\n' "make test"
        else
            printf '%s\n' "make check"
        fi
    fi

    if [ -f "$TARGET_PROJECT/package.json" ]; then
        if grep -q '"lint"' "$TARGET_PROJECT/package.json" 2>/dev/null; then
            if [ -f "$TARGET_PROJECT/pnpm-lock.yaml" ]; then
                printf '%s\n' "pnpm run lint"
            elif [ -f "$TARGET_PROJECT/yarn.lock" ]; then
                printf '%s\n' "yarn lint"
            else
                printf '%s\n' "npm run lint --if-present"
            fi
        fi
        if grep -q '"test"' "$TARGET_PROJECT/package.json" 2>/dev/null; then
            if [ -f "$TARGET_PROJECT/pnpm-lock.yaml" ]; then
                printf '%s\n' "pnpm test"
            elif [ -f "$TARGET_PROJECT/yarn.lock" ]; then
                printf '%s\n' "yarn test"
            else
                printf '%s\n' "npm test --if-present"
            fi
        fi
    fi

    if [ -f "$TARGET_PROJECT/Cargo.toml" ]; then
        printf '%s\n' "cargo test"
    fi

    if [ -f "$TARGET_PROJECT/go.mod" ]; then
        printf '%s\n' "go test ./..."
    fi

    if [ -f "$TARGET_PROJECT/pyproject.toml" ] || [ -f "$TARGET_PROJECT/requirements.txt" ]; then
        if [ -d "$TARGET_PROJECT/tests" ] || [ -f "$TARGET_PROJECT/pytest.ini" ]; then
            printf '%s\n' "pytest -q"
        fi
    fi
}

run_validation() {
    local label="$1"
    local command="$2"

    VALIDATION_LABELS+=("$label")
    kc_run_shell_command "$label" "$command" "$TARGET_PROJECT"
    VALIDATION_RESULTS+=("$label:$KC_COMMAND_STATUS")
    if [ "$KC_COMMAND_STATUS" = "failed" ]; then
        kc_err "$KC_COMMAND_OUTPUT"
        kc_fail "Validation failed: $label"
    fi
}

validation_commands="$(detect_validation_commands | awk 'NF && !seen[$0]++ { print $0 }')"
if [ -n "$validation_commands" ]; then
    while IFS= read -r command; do
        [ -n "$command" ] || continue
        run_validation "$command" "$command"
    done <<EOF
$validation_commands
EOF
else
    WARNINGS+=("No standard validation commands were detected.")
fi

validate_args=(--project "$TARGET_PROJECT")
if [ "$DRY_RUN" -eq 1 ]; then
    validate_args+=(--dry-run)
fi
kc_run_child_script "$SCRIPT_DIR/validate-knowledge.sh" "${validate_args[@]}"

sync_args=(--project "$TARGET_PROJECT" --compact)
if [ "$DRY_RUN" -eq 1 ]; then
    sync_args+=(--dry-run)
fi
kc_run_child_script "$SCRIPT_DIR/update-knowledge.sh" "${sync_args[@]}"

status_lines="$(git -C "$TARGET_PROJECT" status --short)"
changed_files="$(kc_git_changed_files || true)"

if [ -z "$status_lines" ]; then
    WARNINGS+=("No repo changes to commit after validation and knowledge sync.")
fi

if [ -z "$COMMIT_MESSAGE" ]; then
    scope="$(printf '%s\n' "$changed_files" | awk -F/ 'NF { print $1 }' | grep -v '^agent-knowledge$' | awk '!seen[$0]++' | head -3 | paste -sd ', ' -)"
    if [ -n "$scope" ]; then
        COMMIT_MESSAGE="chore: ship $scope updates"
    else
        COMMIT_MESSAGE="chore: sync project knowledge"
    fi
fi

knowledge_external=0
case "$KNOWLEDGE_REAL_DIR" in
    "$TARGET_PROJECT"/*)
        knowledge_external=0
        ;;
    *)
        knowledge_external=1
        WARNINGS+=("Knowledge source of truth lives outside the repo and is not staged here: $KNOWLEDGE_REAL_DIR")
        ;;
esac

if [ -n "$status_lines" ]; then
    kc_run_shell_command "git add" "git add -A" "$TARGET_PROJECT"
    [ "$KC_COMMAND_STATUS" != "failed" ] || kc_fail "git add failed."

    kc_run_shell_command "git commit" "git commit -m \"$(printf '%s' "$COMMIT_MESSAGE" | sed 's/"/\\"/g')\"" "$TARGET_PROJECT"
    if [ "$KC_COMMAND_STATUS" = "failed" ]; then
        if printf '%s' "$KC_COMMAND_OUTPUT" | grep -qi 'nothing to commit'; then
            WARNINGS+=("git commit reported nothing to commit.")
        else
            kc_err "$KC_COMMAND_OUTPUT"
            kc_fail "git commit failed."
        fi
    fi
fi

if git -C "$TARGET_PROJECT" remote get-url origin >/dev/null 2>&1; then
    upstream="$(git -C "$TARGET_PROJECT" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
    if [ -n "$upstream" ]; then
        kc_run_shell_command "git push" "git push" "$TARGET_PROJECT"
    else
        kc_run_shell_command "git push -u" "git push -u origin $branch" "$TARGET_PROJECT"
    fi
else
    WARNINGS+=("No origin remote configured; push skipped.")
fi

should_open_pr=0
if [ "$OPEN_PR_MODE" = "yes" ]; then
    should_open_pr=1
elif [ "$OPEN_PR_MODE" = "auto" ] && command -v gh >/dev/null 2>&1 && [ "$branch" != "main" ] && [ "$branch" != "master" ]; then
    should_open_pr=1
fi

if [ "$should_open_pr" -eq 1 ]; then
    if command -v gh >/dev/null 2>&1; then
        kc_run_shell_command "gh pr create" "gh pr create --fill" "$TARGET_PROJECT"
    else
        WARNINGS+=("GitHub CLI is unavailable; PR creation skipped.")
    fi
fi

json_summary="{"
json_summary="$json_summary\"script\":\"ship\","
json_summary="$json_summary\"project_root\":\"$(kc_json_escape "$TARGET_PROJECT")\","
json_summary="$json_summary\"branch\":\"$(kc_json_escape "$branch")\","
json_summary="$json_summary\"commit_message\":\"$(kc_json_escape "$COMMIT_MESSAGE")\","
json_summary="$json_summary\"dry_run\":$(kc_json_bool "$DRY_RUN"),"
json_summary="$json_summary\"knowledge_external\":$(kc_json_bool "$knowledge_external"),"
json_summary="$json_summary\"validations\":$(kc_json_array "${VALIDATION_RESULTS[@]+"${VALIDATION_RESULTS[@]}"}"),"
json_summary="$json_summary\"warnings\":$(kc_json_array "${WARNINGS[@]+"${WARNINGS[@]}"}")"
json_summary="$json_summary}"
kc_write_json_output "$json_summary"

if [ "$JSON_MODE" -ne 1 ]; then
    kc_log "Ship summary: $TARGET_PROJECT"
    kc_log "  branch: $branch"
    kc_log "  commit message: $COMMIT_MESSAGE"
    if [ ${#VALIDATION_RESULTS[@]} -gt 0 ]; then
        kc_log "  validations:"
        printf '    %s\n' "${VALIDATION_RESULTS[@]+"${VALIDATION_RESULTS[@]}"}"
    fi
    if [ ${#WARNINGS[@]} -gt 0 ]; then
        kc_log "  warnings:"
        printf '    %s\n' "${WARNINGS[@]+"${WARNINGS[@]}"}"
    fi
fi
