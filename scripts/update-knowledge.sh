#!/bin/bash
#
# Project-level knowledge refresh.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENTS_RULES_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DECISION_TEMPLATE="$AGENTS_RULES_DIR/templates/memory/decision.template.md"
# shellcheck source=/dev/null
. "$SCRIPT_DIR/lib/knowledge-common.sh"

usage() {
    cat <<'EOF'
Usage:
  scripts/update-knowledge.sh [project-dir]
  scripts/update-knowledge.sh --project <dir> [--decision-title <title>] [--decision-why <text>] [--compact] [--dry-run] [--json] [--summary-file <file>]
EOF
}

TARGET_PROJECT_ARG="."
POSITIONAL=()
DECISION_TITLE=""
DECISION_WHY=""
DECISION_SLUG=""
RUN_COMPACTION=0
UPDATED_NOTES=()
SKIPPED=()
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
        --decision-title)
            DECISION_TITLE="${2:-}"
            shift 2
            ;;
        --decision-why)
            DECISION_WHY="${2:-}"
            shift 2
            ;;
        --decision-slug)
            DECISION_SLUG="${2:-}"
            shift 2
            ;;
        --compact)
            RUN_COMPACTION=1
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

if [ ! -e "$KNOWLEDGE_POINTER_PATH" ]; then
    kc_fail "Missing ./agent-knowledge pointer. Run scripts/install-project-links.sh first."
fi

kc_require_knowledge_pointer

if [ ! -f "$MEMORY_ROOT" ] || [ ! -f "$STATUS_FILE" ]; then
    bootstrap_args=(--project "$TARGET_PROJECT")
    if [ "$DRY_RUN" -eq 1 ]; then
        bootstrap_args+=(--dry-run)
    fi
    "$SCRIPT_DIR/bootstrap-memory-tree.sh" "${bootstrap_args[@]}"
    kc_load_project_context "$TARGET_PROJECT"
    kc_require_knowledge_pointer
fi

changed_files="$(kc_git_changed_files || true)"

format_paths_inline() {
    local paths_text="$1"
    local limit="$2"
    local count=0
    local line=""
    local output=""

    while IFS= read -r line; do
        [ -n "$line" ] || continue
        count=$((count + 1))
        if [ "$count" -le "$limit" ]; then
            if [ -n "$output" ]; then
                output="$output, "
            fi
            output="$output\`$line\`"
        fi
    done <<EOF
$paths_text
EOF

    if [ "$count" -gt "$limit" ]; then
        output="$output, ..."
    fi
    printf '%s' "$output"
}

classify_path() {
    local path="$1"
    local areas=""
    local existing=""

    case "$path" in
        agent-knowledge/*)
            return 0
            ;;
        .github/workflows/*|deploy/*|deployment/*|infra/*)
            areas="deployments"$'\n'"architecture"
            ;;
        package.json|package-lock.json|pnpm-lock.yaml|yarn.lock|pnpm-workspace.yaml|nx.json|turbo.json|pyproject.toml|requirements.txt|Cargo.toml|go.mod|CMakeLists.txt|package.xml|Makefile)
            areas="stack"
            ;;
        *.eslintrc|*.eslintrc.js|*.eslintrc.cjs|eslint.config.js|eslint.config.mjs|eslint.config.cjs|.editorconfig|.prettierrc|.prettierrc.json|.prettierrc.yaml|tsconfig.json|tsconfig.base.json|pytest.ini|mypy.ini|ruff.toml|.clang-format|.clang-tidy|.pre-commit-config.yaml)
            areas="conventions"
            ;;
        README.md|README.rst|AGENTS.md|CLAUDE.md|docs/*|src/*|app/*|apps/*|services/*|packages/*)
            areas="architecture"
            ;;
        urdf/*|meshes/*|hardware/*|robot/*)
            areas="hardware"
            ;;
        launch/*|simulation/*|sim/*|worlds/*|gazebo/*|ign/*)
            areas="simulation"
            ;;
        data/*|datasets/*|notebooks/*)
            areas="datasets"
            ;;
        models/*|checkpoints/*|artifacts/*)
            areas="models"
            ;;
        *)
            areas="architecture"
            ;;
    esac

    while IFS= read -r existing; do
        [ -n "$existing" ] || continue
        if [ -f "$MEMORY_DIR/$existing.md" ]; then
            printf '%s\n' "$existing"
        fi
    done <<EOF
$areas
EOF
}

append_note_change() {
    local file="$1"
    local bullet="$2"
    local rel
    rel="$(kc_rel_knowledge_path "$file")"
    kc_append_unique_bullet "$file" "Recent Changes" "$bullet" "$rel"
    case "$KC_LAST_ACTION" in
        updated|would-update)
            UPDATED_NOTES+=("$rel")
            ;;
    esac
}

render_decision_note() {
    local title="$1"
    local why="$2"
    local slug="$3"
    local dst="$DECISIONS_DIR/$slug.md"
    local tmp_file

    tmp_file="$(mktemp)"
    TEMPLATE_PROJECT_NAME="$PROJECT_NAME" \
    TEMPLATE_PROFILE="$PROJECT_PROFILE" \
    TEMPLATE_DATE="$(kc_today)" \
    TEMPLATE_DECISION_SLUG="$slug" \
    TEMPLATE_SHORT_TITLE="$title" \
    TEMPLATE_WHAT_LINES="- Triggered by project knowledge sync for changed files." \
    TEMPLATE_WHY_LINES="- ${why:-Durable understanding changed enough to justify a recorded note.}" \
    TEMPLATE_ALTERNATIVES_LINES="- Record the change only in recent-change bullets." \
    TEMPLATE_CONSEQUENCES_LINES="- Future sessions can link a concrete decision instead of inferring intent from evidence alone." \
    TEMPLATE_SUPERSEDED_LINES="- None." \
    awk '
        BEGIN {
            project = ENVIRON["TEMPLATE_PROJECT_NAME"]
            profile = ENVIRON["TEMPLATE_PROFILE"]
            date = ENVIRON["TEMPLATE_DATE"]
            decision_slug = ENVIRON["TEMPLATE_DECISION_SLUG"]
            short_title = ENVIRON["TEMPLATE_SHORT_TITLE"]
            what_lines = ENVIRON["TEMPLATE_WHAT_LINES"]
            why_lines = ENVIRON["TEMPLATE_WHY_LINES"]
            alternatives_lines = ENVIRON["TEMPLATE_ALTERNATIVES_LINES"]
            consequences_lines = ENVIRON["TEMPLATE_CONSEQUENCES_LINES"]
            superseded_lines = ENVIRON["TEMPLATE_SUPERSEDED_LINES"]
        }
        {
            gsub(/<project-name>/, project)
            gsub(/<profile-type>/, profile)
            gsub(/<date>/, date)
            gsub(/<decision-slug>/, decision_slug)
            gsub(/<short-title>/, short_title)
            if ($0 == "<what-lines>") { print what_lines; next }
            if ($0 == "<why-lines>") { print why_lines; next }
            if ($0 == "<alternatives-lines>") { print alternatives_lines; next }
            if ($0 == "<consequences-lines>") { print consequences_lines; next }
            if ($0 == "<superseded-lines>") { print superseded_lines; next }
            print
        }
    ' "$DECISION_TEMPLATE" > "$tmp_file"

    kc_apply_temp_file "$tmp_file" "$dst" "Memory/decisions/$slug.md"
    case "$KC_LAST_ACTION" in
        created|updated|would-create|would-update)
            UPDATED_NOTES+=("Memory/decisions/$slug.md")
            ;;
    esac

    kc_append_unique_bullet "$DECISIONS_DIR/INDEX.md" "Current State" "- [$title]($slug.md) - Recorded from project sync." "Memory/decisions/INDEX.md"
    kc_append_unique_bullet "$DECISIONS_DIR/INDEX.md" "Recent Changes" "- $(kc_today) - Updated decision note [$title]($slug.md)." "Memory/decisions/INDEX.md"
}

affected_areas_raw=""
if [ -n "$changed_files" ]; then
    while IFS= read -r path; do
        [ -n "$path" ] || continue
        area_lines="$(classify_path "$path")"
        if [ -n "$area_lines" ]; then
            affected_areas_raw="${affected_areas_raw}${area_lines}"$'\n'
        else
            SKIPPED+=("$path")
        fi
    done <<EOF
$changed_files
EOF
else
    WARNINGS+=("No git-tracked project changes detected; evidence refresh still ran.")
fi

affected_areas="$(printf '%s\n' "$affected_areas_raw" | awk 'NF && !seen[$0]++ { print $0 }')"
changed_paths_summary="$(format_paths_inline "$changed_files" 5)"

if [ -n "$affected_areas" ]; then
    while IFS= read -r area; do
        [ -n "$area" ] || continue
        note_path="$MEMORY_DIR/$area.md"
        if [ -f "$note_path" ]; then
            append_note_change "$note_path" "- $(kc_today) - Synced after changes in $changed_paths_summary."
        else
            WARNINGS+=("Skipped missing area note for $area")
        fi
    done <<EOF
$affected_areas
EOF

    areas_summary="$(printf '%s\n' "$affected_areas" | awk 'NF { items[++count]=$0 } END { for (i=1;i<=count;i++) { printf "`%s`", items[i]; if (i < count) printf ", " } }')"
    append_note_change "$MEMORY_ROOT" "- $(kc_today) - Knowledge sync touched $areas_summary from $changed_paths_summary."
else
    append_note_change "$MEMORY_ROOT" "- $(kc_today) - Knowledge sync ran with no new durable branch updates."
fi

if [ -n "$DECISION_TITLE" ]; then
    if [ -z "$DECISION_SLUG" ]; then
        DECISION_SLUG="$(kc_slugify "$DECISION_TITLE")"
    fi
    render_decision_note "$DECISION_TITLE" "$DECISION_WHY" "$DECISION_SLUG"
else
    WARNINGS+=("No decision note update requested.")
fi

import_args=(--project "$TARGET_PROJECT")
if [ "$DRY_RUN" -eq 1 ]; then
    import_args+=(--dry-run)
fi
kc_run_child_script "$SCRIPT_DIR/import-agent-history.sh" "${import_args[@]}"

if [ "$RUN_COMPACTION" -eq 1 ]; then
    compact_args=(--project "$TARGET_PROJECT")
    if [ "$DRY_RUN" -eq 1 ]; then
        compact_args+=(--dry-run)
    fi
    kc_run_child_script "$SCRIPT_DIR/compact-memory.sh" "${compact_args[@]}"
fi

kc_status_load
if [ "${DRY_RUN:-0}" -eq 0 ]; then
    STATUS_LAST_PROJECT_SYNC="$(kc_now_utc)"
fi
STATUS_WARNING_LINES="$(printf '%s\n' "${WARNINGS[@]+"${WARNINGS[@]}"}")"
kc_status_write "$STATUS_WARNING_LINES"

json_summary="{"
json_summary="$json_summary\"script\":\"update-knowledge\","
json_summary="$json_summary\"project_root\":\"$(kc_json_escape "$TARGET_PROJECT")\","
json_summary="$json_summary\"dry_run\":$(kc_json_bool "$DRY_RUN"),"
json_summary="$json_summary\"changed_files\":$(kc_json_array_from_lines "$changed_files"),"
json_summary="$json_summary\"affected_areas\":$(kc_json_array_from_lines "$affected_areas"),"
json_summary="$json_summary\"updated_notes\":$(kc_json_array "${UPDATED_NOTES[@]+"${UPDATED_NOTES[@]}"}"),"
json_summary="$json_summary\"skipped\":$(kc_json_array "${SKIPPED[@]+"${SKIPPED[@]}"}"),"
json_summary="$json_summary\"warnings\":$(kc_json_array "${WARNINGS[@]+"${WARNINGS[@]}"}")"
json_summary="$json_summary}"
kc_write_json_output "$json_summary"

if [ "$JSON_MODE" -ne 1 ]; then
    kc_log "Knowledge sync: $TARGET_PROJECT"
    if [ -n "$changed_files" ]; then
        kc_log "Changed files:"
        while IFS= read -r path; do
            [ -n "$path" ] || continue
            kc_log "  $path"
        done <<EOF
$changed_files
EOF
    fi

    kc_log ""
    if [ ${#UPDATED_NOTES[@]} -gt 0 ]; then
        kc_log "Updated memory notes:"
        printf '  %s\n' "${UPDATED_NOTES[@]+"${UPDATED_NOTES[@]}"}"
    else
        kc_log "No durable memory note changes were required."
    fi

    if [ ${#SKIPPED[@]} -gt 0 ]; then
        kc_log ""
        kc_log "Skipped:"
        printf '  %s\n' "${SKIPPED[@]+"${SKIPPED[@]}"}"
    fi
fi
