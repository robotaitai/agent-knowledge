#!/bin/bash
#
# Collect project evidence into bedrock/Evidence/raw/ and imports/.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
. "$SCRIPT_DIR/lib/knowledge-common.sh"

usage() {
    cat <<'EOF'
Usage:
  scripts/import-agent-history.sh [project-dir]
  scripts/import-agent-history.sh --project <dir> [--dry-run] [--json] [--summary-file <file>]
EOF
}

TARGET_PROJECT_ARG="."
POSITIONAL=()
GENERATED=()
RAW_GENERATED=()
IMPORT_GENERATED=()
OUTPUT_GENERATED=()
CACHED=()
WARNINGS=()
SKIPPED=()
DATE="$(kc_today)"
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
kc_ensure_dir "$EVIDENCE_RAW_DIR" "bedrock/Evidence/raw"
kc_ensure_dir "$EVIDENCE_IMPORTS_DIR" "bedrock/Evidence/imports"
kc_ensure_dir "$OUTPUTS_DIR" "bedrock/Outputs"
kc_ensure_dir "$EVIDENCE_CACHE_DIR" "bedrock/Evidence/.cache"

PROJECT_LABEL="$(basename "$TARGET_PROJECT")"

relative_path() {
    sed "s|$TARGET_PROJECT/||" | sed "s|^$TARGET_PROJECT$|.|"
}

header() {
    local title="$1"
    local source="$2"
    local kind="$3"
    local confidence="$4"
    printf '# Evidence: %s\n' "$title"
    printf '# Source: %s\n' "$source"
    printf '# Kind: %s\n' "$kind"
    printf '# Confidence: %s\n' "$confidence"
    printf '# Generated: %s\n' "$GENERATED_AT"
    printf '# Project: %s\n\n' "$PROJECT_LABEL"
}

list_existing_paths() {
    local base="$1"
    shift
    local path=""
    local rel=""

    for path in "$@"; do
        rel="$(kc_normalize_relative_path "$path")"
        [ -e "$base/$rel" ] || continue
        if kc_path_is_ignored "$rel"; then
            SKIPPED+=("$rel")
            continue
        fi
        printf '%s\n' "$rel"
    done
}

list_top_level_dirs() {
    find "$TARGET_PROJECT" -mindepth 1 -maxdepth 1 -type d 2>/dev/null \
        | relative_path \
        | grep -Ev '^(bedrock|node_modules|vendor|\.git|\.cursor|dist|build|\.next|__pycache__|\.venv)$' \
        | kc_filter_relative_lines \
        | sort
}

find_relative() {
    local maxdepth="$1"
    shift
    find "$TARGET_PROJECT" "$@" -maxdepth "$maxdepth" 2>/dev/null \
        | relative_path \
        | kc_filter_relative_lines \
        | sort
}

find_any_relative() {
    find "$TARGET_PROJECT" "$@" 2>/dev/null \
        | relative_path \
        | kc_filter_relative_lines \
        | sort
}

project_profile_guess() {
    local manifest_total=0

    manifest_total="$(printf '%s\n' "$MANIFEST_PATHS" | awk 'NF { count++ } END { print count + 0 }')"

    if printf '%s\n' "$MANIFEST_PATHS" "$TEST_PATHS" "$TOP_LEVEL_DIRS" | grep -Eq '(^|/)(package\.xml|launch|urdf|simulation|gazebo|worlds)$' || \
       printf '%s\n' "$MANIFEST_PATHS" | grep -q '^CMakeLists.txt$'; then
        printf 'robotics\n'
        return
    fi

    if printf '%s\n' "$MANIFEST_PATHS" "$TOP_LEVEL_DIRS" | grep -Eq '(^|/)(pyproject\.toml|requirements\.txt|notebooks|models|data)$'; then
        printf 'ml-platform\n'
        return
    fi

    if printf '%s\n' "$MANIFEST_PATHS" "$TOP_LEVEL_DIRS" | grep -Eq '(^|/)(pnpm-workspace\.yaml|nx\.json|turbo\.json|packages|services|apps)$' || [ "$manifest_total" -ge 3 ]; then
        printf 'hybrid\n'
        return
    fi

    if printf '%s\n' "$MANIFEST_PATHS" | grep -q '^package.json$'; then
        printf 'web-app\n'
        return
    fi

    printf '%s\n' "${PROJECT_PROFILE:-unknown}"
}

render_manifest_contents() {
    local rel=""

    while IFS= read -r rel; do
        [ -n "$rel" ] || continue
        printf '=== %s ===\n' "$rel"
        if [ "$(wc -l < "$TARGET_PROJECT/$rel")" -gt 200 ]; then
            head -60 "$TARGET_PROJECT/$rel"
            printf '... (truncated at 60 lines)\n'
        else
            cat "$TARGET_PROJECT/$rel"
        fi
        printf '\n'
    done <<EOF
$MANIFEST_PATHS
EOF
}

render_doc_contents() {
    local rel=""

    while IFS= read -r rel; do
        [ -n "$rel" ] || continue
        printf '=== %s ===\n' "$rel"
        if [ "$(wc -l < "$TARGET_PROJECT/$rel")" -gt 300 ]; then
            head -100 "$TARGET_PROJECT/$rel"
            printf '... (truncated at 100 lines)\n'
        else
            cat "$TARGET_PROJECT/$rel"
        fi
        printf '\n'
    done <<EOF
$DOC_IMPORT_PATHS
EOF
}

capture_text_artifact() {
    local namespace="$1"
    local key="$2"
    local dst="$3"
    local label="$4"
    local bucket="$5"
    local source="$6"
    local kind="$7"
    local confidence="$8"
    local related_paths="$9"
    local notes="${10:-}"
    local signature="${11:-}"
    local meta_dst="$dst.meta.json"
    local tmp_file=""
    local changed=0

    if kc_cache_is_current "$namespace" "$key" "$signature" "$dst" "$meta_dst"; then
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

    kc_write_metadata_json "$meta_dst" "$label.meta.json" "$source" "$kind" "$confidence" "$GENERATED_AT" "$related_paths" "$notes"
    case "$KC_LAST_ACTION" in
        created|updated|would-create|would-update)
            changed=1
            ;;
    esac

    kc_cache_store "$namespace" "$key" "$signature"

    if [ "$changed" -eq 1 ]; then
        GENERATED+=("$label")
        case "$bucket" in
            raw)
                RAW_GENERATED+=("$label")
                ;;
            imports)
                IMPORT_GENERATED+=("$label")
                ;;
            outputs)
                OUTPUT_GENERATED+=("$label")
                ;;
        esac
    fi
}

capture_markdown_note() {
    local namespace="$1"
    local key="$2"
    local dst="$3"
    local label="$4"
    local bucket="$5"
    local source="$6"
    local kind="$7"
    local confidence="$8"
    local related_paths="$9"
    local notes="${10}"
    local signature="${11}"
    local tmp_file=""
    local changed=0

    if kc_cache_is_current "$namespace" "$key" "$signature" "$dst"; then
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

    kc_cache_store "$namespace" "$key" "$signature"

    if [ "$changed" -eq 1 ]; then
        GENERATED+=("$label")
        case "$bucket" in
            imports)
                IMPORT_GENERATED+=("$label")
                ;;
            outputs)
                OUTPUT_GENERATED+=("$label")
                ;;
        esac
    fi
}

MANIFEST_PATHS="$(list_existing_paths "$TARGET_PROJECT" \
    package.json package-lock.json pnpm-lock.yaml yarn.lock pnpm-workspace.yaml nx.json turbo.json \
    pyproject.toml requirements.txt setup.py setup.cfg Pipfile poetry.lock \
    Cargo.toml Cargo.lock go.mod go.sum CMakeLists.txt Makefile package.xml)"
DOC_IMPORT_PATHS="$(list_existing_paths "$TARGET_PROJECT" \
    README.md README.rst CLAUDE.md AGENTS.md .agent-project.yaml .cursorrules \
    bedrock/INDEX.md bedrock/Memory/PROJECT.md bedrock/Memory/MEMORY.md docs/README.md)"
CONFIG_PATHS="$(find "$TARGET_PROJECT" -maxdepth 2 \( \
    -name ".editorconfig" -o \
    -name ".clang-format" -o \
    -name ".clang-tidy" -o \
    -name ".eslintrc" -o \
    -name ".eslintrc.js" -o \
    -name ".eslintrc.cjs" -o \
    -name "eslint.config.js" -o \
    -name "eslint.config.mjs" -o \
    -name "eslint.config.cjs" -o \
    -name ".prettierrc" -o \
    -name ".prettierrc.json" -o \
    -name ".prettierrc.yaml" -o \
    -name ".pre-commit-config.yaml" -o \
    -name "pytest.ini" -o \
    -name "mypy.ini" -o \
    -name "ruff.toml" -o \
    -name "tsconfig.json" -o \
    -name "tsconfig.base.json" \) 2>/dev/null | relative_path | kc_filter_relative_lines | sort)"
TEST_PATHS="$(find "$TARGET_PROJECT" -maxdepth 3 -type d \( \
    -name "test" -o \
    -name "tests" -o \
    -name "__tests__" -o \
    -name "spec" -o \
    -name "specs" -o \
    -name "integration-tests" -o \
    -name "launch" -o \
    -name "simulation" -o \
    -name "notebooks" -o \
    -name "models" -o \
    -name "data" \) 2>/dev/null | relative_path | kc_filter_relative_lines | sort)"
WORKFLOW_PATHS="$(if [ -d "$TARGET_PROJECT/.github/workflows" ]; then
    find "$TARGET_PROJECT/.github/workflows" -mindepth 1 -maxdepth 1 -type f 2>/dev/null | relative_path | kc_filter_relative_lines | sort
fi)"
STRUCTURE_PATHS="$(find "$TARGET_PROJECT" \
    -maxdepth 4 \
    -not -path "*/.git/*" \
    -not -path "*/node_modules/*" \
    -not -path "*/vendor/*" \
    -not -path "*/__pycache__/*" \
    -not -path "*/.venv/*" \
    -not -path "*/dist/*" \
    -not -path "*/.next/*" \
    -not -path "*/build/*" \
    | sort | relative_path | grep -Ev '^bedrock($|/)' | kc_filter_relative_lines)"
TOP_LEVEL_DIRS="$(list_top_level_dirs)"
DOC_INDEX_PATHS="$(find_any_relative \
    -name "*.md" \
    -not -path "*/node_modules/*" \
    -not -path "*/.git/*" \
    -not -path "*/vendor/*")"
# Guard both finds on the directory existing: under `set -o pipefail` a find
# over a missing path fails the whole command substitution and aborts the run,
# which is how `bedrock update` came to exit 1 in any repo without a tasks/ dir.
TASK_PATHS="$(if [ -d "$TARGET_PROJECT/tasks" ]; then
    find "$TARGET_PROJECT/tasks" -mindepth 1 -maxdepth 2 -type f 2>/dev/null | relative_path | kc_filter_relative_lines | sort
fi)"
# Sessions/ is a legacy vault folder; the shared lib stopped defining a path for
# it when the cockpit was simplified, so resolve it here for older vaults.
SESSIONS_DIR="${SESSIONS_DIR:-$KNOWLEDGE_DIR/Sessions}"
SESSION_FILE_PATHS="$(if [ -d "$SESSIONS_DIR" ]; then
    find "$SESSIONS_DIR" -mindepth 1 -maxdepth 1 -type f 2>/dev/null | relative_path | kc_filter_relative_lines | sort
fi)"
TRACE_PATHS="$(for d in agent-traces traces logs/agent bedrock/Outputs/traces; do
    if [ -d "$TARGET_PROJECT/$d" ] && ! kc_path_is_ignored "$d"; then
        find "$TARGET_PROJECT/$d" -type f 2>/dev/null | relative_path | kc_filter_relative_lines
    fi
done | sort)"

LIKELY_PROFILE="$(project_profile_guess)"
ARCH_SUMMARY_RELATED="$(printf '%s\n%s\n%s\n%s\n' "$MANIFEST_PATHS" "$DOC_IMPORT_PATHS" "$TOP_LEVEL_DIRS" "$WORKFLOW_PATHS" | awk 'NF && !seen[$0]++ { print $0 }')"

kc_log "Collecting evidence: $PROJECT_LABEL"
kc_log ""
if [ -f "$IGNORE_FILE" ]; then
    WARNINGS+=("history import is honoring .agentknowledgeignore")
fi

if kc_git_available; then
    if kc_git_has_commits; then
        GIT_SIGNATURE="$(printf '%s\n%s\n' "$(git -C "$TARGET_PROJECT" rev-parse HEAD)" "$(git -C "$TARGET_PROJECT" rev-list --count HEAD 2>/dev/null || echo 0)" | kc_hash_text)"
        capture_text_artifact "history-import" "git-log" "$EVIDENCE_RAW_DIR/git-log.txt" "bedrock/Evidence/raw/git-log.txt" "raw" "git" "git-log" "EXTRACTED" ".git" "Last 300 commits in oneline form. Review as evidence, not canonical truth." "$GIT_SIGNATURE" <<EOF
$(header "git-log (oneline, last 300)" "git" "git-log" "EXTRACTED")
$(git -C "$TARGET_PROJECT" log --oneline -300)
EOF

        capture_text_artifact "history-import" "git-log-detail" "$EVIDENCE_RAW_DIR/git-log-detail.txt" "bedrock/Evidence/raw/git-log-detail.txt" "raw" "git" "git-log-detail" "EXTRACTED" ".git" "Detailed commit evidence with subject and body for the most recent history slice." "$GIT_SIGNATURE" <<EOF
$(header "git-log-detail (last 50, with body)" "git" "git-log-detail" "EXTRACTED")
$(git -C "$TARGET_PROJECT" log -50 --pretty=format:"----%ncommit %h%nDate:   %ai%nAuthor: %an%n%n%s%n%b")
EOF

        capture_text_artifact "history-import" "git-authors" "$EVIDENCE_RAW_DIR/git-authors.txt" "bedrock/Evidence/raw/git-authors.txt" "raw" "git" "git-authors" "EXTRACTED" ".git" "Unique git authors extracted from repository history." "$GIT_SIGNATURE" <<EOF
$(header "git-authors" "git" "git-authors" "EXTRACTED")
$(git -C "$TARGET_PROJECT" log --pretty=format:"%an <%ae>" | sort -u)
EOF
    else
        WARNINGS+=("git evidence skipped because the repository has no commits yet")
        kc_log "  note: git evidence skipped (repository has no commits yet)"
    fi
else
    WARNINGS+=("git evidence skipped because the target is not a git repo")
    kc_log "  note: git evidence skipped (not a git repo)"
fi

STRUCTURE_SIGNATURE="$(kc_signature_from_project_relative_lines "$STRUCTURE_PATHS")"
capture_text_artifact "history-import" "structure" "$EVIDENCE_RAW_DIR/structure.txt" "bedrock/Evidence/raw/structure.txt" "raw" "repo-scan" "directory-structure" "EXTRACTED" "$TOP_LEVEL_DIRS" "Top-level directories and immediate structural signals from the current repo." "$STRUCTURE_SIGNATURE" <<EOF
$(header "structure (top-level and depth 4 overview)" "repo-scan" "directory-structure" "EXTRACTED")
## Top-level Directories
$(if [ -n "$TOP_LEVEL_DIRS" ]; then printf '%s\n' "$TOP_LEVEL_DIRS"; else printf '(none)\n'; fi)

## Depth-4 Structure
$(printf '%s\n' "$STRUCTURE_PATHS")
EOF

MANIFEST_SIGNATURE="$(kc_signature_from_project_relative_lines "$MANIFEST_PATHS")"
capture_text_artifact "history-import" "manifests" "$EVIDENCE_RAW_DIR/manifests.txt" "bedrock/Evidence/raw/manifests.txt" "raw" "repo-scan" "manifests" "EXTRACTED" "$MANIFEST_PATHS" "Dependency and manifest files copied with truncation for very large files." "$MANIFEST_SIGNATURE" <<EOF
$(header "manifests" "repo-scan" "manifests" "EXTRACTED")
$(if [ -n "$MANIFEST_PATHS" ]; then render_manifest_contents; else echo "(no manifests found)"; fi)
EOF

CONFIG_SIGNATURE="$(kc_signature_from_project_relative_lines "$CONFIG_PATHS")"
capture_text_artifact "history-import" "config-files" "$EVIDENCE_RAW_DIR/config-files.txt" "bedrock/Evidence/raw/config-files.txt" "raw" "repo-scan" "config-files" "EXTRACTED" "$CONFIG_PATHS" "Config files that usually define linting, formatting, typing, or build conventions." "$CONFIG_SIGNATURE" <<EOF
$(header "config-files" "repo-scan" "config-files" "EXTRACTED")
$(if [ -n "$CONFIG_PATHS" ]; then printf '%s\n' "$CONFIG_PATHS"; else echo "(no matching config files found)"; fi)
EOF

TEST_SIGNATURE="$(kc_signature_from_project_relative_lines "$TEST_PATHS")"
capture_text_artifact "history-import" "tests" "$EVIDENCE_RAW_DIR/tests.txt" "bedrock/Evidence/raw/tests.txt" "raw" "repo-scan" "test-surfaces" "EXTRACTED" "$TEST_PATHS" "Directories that suggest tests, launches, simulations, datasets, or model assets." "$TEST_SIGNATURE" <<EOF
$(header "tests" "repo-scan" "test-surfaces" "EXTRACTED")
$(if [ -n "$TEST_PATHS" ]; then printf '%s\n' "$TEST_PATHS"; else echo "(no matching test or validation directories found)"; fi)
EOF

WORKFLOW_SIGNATURE="$(kc_signature_from_project_relative_lines "$WORKFLOW_PATHS")"
capture_text_artifact "history-import" "ci-workflows" "$EVIDENCE_RAW_DIR/ci-workflows.txt" "bedrock/Evidence/raw/ci-workflows.txt" "raw" "repo-scan" "ci-workflows" "EXTRACTED" "$WORKFLOW_PATHS" "Workflow definitions that shape validation and deployment behavior." "$WORKFLOW_SIGNATURE" <<EOF
$(header "ci-workflows" "repo-scan" "ci-workflows" "EXTRACTED")
$(if [ -n "$WORKFLOW_PATHS" ]; then
    while IFS= read -r rel; do
        [ -n "$rel" ] || continue
        echo "=== $rel ==="
        if [ "$(wc -l < "$TARGET_PROJECT/$rel")" -gt 150 ]; then
            head -60 "$TARGET_PROJECT/$rel"
            echo "... (truncated)"
        else
            cat "$TARGET_PROJECT/$rel"
        fi
        echo ""
    done <<EOF_INNER
$WORKFLOW_PATHS
EOF_INNER
else
    echo "(no .github/workflows found)"
fi)
EOF

DOC_SIGNATURE="$(kc_signature_from_project_relative_lines "$DOC_IMPORT_PATHS")"
capture_text_artifact "history-import" "existing-docs" "$EVIDENCE_IMPORTS_DIR/existing-docs.txt" "bedrock/Evidence/imports/existing-docs.txt" "imports" "repo-scan" "existing-docs" "EXTRACTED" "$DOC_IMPORT_PATHS" "High-signal docs and local project metadata copied for backfill review." "$DOC_SIGNATURE" <<EOF
$(header "existing-docs" "repo-scan" "existing-docs" "EXTRACTED")
$(if [ -n "$DOC_IMPORT_PATHS" ]; then render_doc_contents; else echo "(no key doc files found)"; fi)
EOF

DOC_INDEX_SIGNATURE="$(kc_signature_from_project_relative_lines "$DOC_INDEX_PATHS")"
capture_text_artifact "history-import" "doc-index" "$EVIDENCE_IMPORTS_DIR/doc-index.txt" "bedrock/Evidence/imports/doc-index.txt" "imports" "repo-scan" "doc-index" "EXTRACTED" "$DOC_INDEX_PATHS" "Markdown path index only. Use this to decide which docs to inspect next." "$DOC_INDEX_SIGNATURE" <<EOF
$(header "doc-index (paths)" "repo-scan" "doc-index" "EXTRACTED")
$(if [ -n "$DOC_INDEX_PATHS" ]; then printf '%s\n' "$DOC_INDEX_PATHS"; else echo "(no markdown files found)"; fi)
EOF

TASK_SIGNATURE="$(kc_signature_from_project_relative_lines "$TASK_PATHS")"
capture_text_artifact "history-import" "tasks" "$EVIDENCE_IMPORTS_DIR/tasks.txt" "bedrock/Evidence/imports/tasks.txt" "imports" "repo-scan" "tasks" "EXTRACTED" "$TASK_PATHS" "Task files can be useful but may lag behind the true project state." "$TASK_SIGNATURE" <<EOF
$(header "tasks" "repo-scan" "tasks" "EXTRACTED")
$(if [ -n "$TASK_PATHS" ]; then
    while IFS= read -r rel; do
        [ -n "$rel" ] || continue
        echo "=== $rel ==="
        cat "$TARGET_PROJECT/$rel"
        echo ""
    done <<EOF_INNER
$TASK_PATHS
EOF_INNER
    if [ -d "$TARGET_PROJECT/tasks" ] && ! kc_path_is_ignored "tasks"; then
        echo "=== tasks/ contents ==="
        ls "$TARGET_PROJECT/tasks/"
    fi
else
    echo "(no tasks/ directory found)"
fi)
EOF

SESSION_SIGNATURE="$(kc_signature_from_project_relative_lines "$SESSION_FILE_PATHS")"
capture_text_artifact "history-import" "session-files" "$EVIDENCE_IMPORTS_DIR/session-files.txt" "bedrock/Evidence/imports/session-files.txt" "imports" "local-knowledge" "session-files" "AMBIGUOUS" "$SESSION_FILE_PATHS" "Session notes are temporary and may contain unresolved or outdated assumptions." "$SESSION_SIGNATURE" <<EOF
$(header "session-files" "local-knowledge" "session-files" "AMBIGUOUS")
$(if [ -n "$SESSION_FILE_PATHS" ]; then
    while IFS= read -r rel; do
        [ -n "$rel" ] || continue
        echo "=== $rel ==="
        if [ "$(wc -l < "$TARGET_PROJECT/$rel")" -gt 120 ]; then
            head -60 "$TARGET_PROJECT/$rel"
            echo "... (truncated at 60 lines)"
        else
            cat "$TARGET_PROJECT/$rel"
        fi
        echo ""
    done <<EOF_INNER
$SESSION_FILE_PATHS
EOF_INNER
else
    echo "(no local Sessions/ files found)"
fi)
EOF

CURSOR_SESSION_LIST="$(
    found=""
    for d in "$HOME"/.cursor/projects/*/sessions; do
        if [ -d "$d" ] && printf '%s' "$d" | grep -qi "$PROJECT_LABEL" 2>/dev/null; then
            echo "$d"
            found="yes"
        fi
    done
    [ -n "$found" ] || true
)"
CURSOR_SESSION_SIGNATURE="$(kc_signature_from_paths $CURSOR_SESSION_LIST)"
capture_text_artifact "history-import" "cursor-sessions" "$EVIDENCE_IMPORTS_DIR/cursor-sessions.txt" "bedrock/Evidence/imports/cursor-sessions.txt" "imports" "cursor" "cursor-session-index" "AMBIGUOUS" "$CURSOR_SESSION_LIST" "Cursor session listings help locate prior work, but session output is not canonical truth." "$CURSOR_SESSION_SIGNATURE" <<EOF
$(header "cursor-sessions" "cursor" "cursor-session-index" "AMBIGUOUS")
$(found=""
for d in "$HOME"/.cursor/projects/*/sessions; do
    if [ -d "$d" ] && printf '%s' "$d" | grep -qi "$PROJECT_LABEL" 2>/dev/null; then
        echo "=== $d ==="
        ls -lt "$d" 2>/dev/null | head -10
        echo ""
        found="yes"
    fi
done
[ -z "$found" ] && echo "(no matching Cursor session dirs found)")
EOF

TRACE_SIGNATURE="$(kc_signature_from_project_relative_lines "$TRACE_PATHS")"
capture_text_artifact "history-import" "trace-index" "$EVIDENCE_IMPORTS_DIR/trace-index.txt" "bedrock/Evidence/imports/trace-index.txt" "imports" "project-traces" "trace-index" "AMBIGUOUS" "$TRACE_PATHS" "Imported traces and generated outputs are evidence only and must be curated before promotion to Memory." "$TRACE_SIGNATURE" <<EOF
$(header "trace-index" "project-traces" "trace-index" "AMBIGUOUS")
$(if [ -n "$TRACE_PATHS" ]; then printf '%s\n' "$TRACE_PATHS"; else echo "(no imported trace directories found)"; fi)
EOF

STRUCTURAL_SUMMARY_SIGNATURE="$(kc_signature_from_lines "$(printf '%s\n---\n%s\n---\n%s\n---\n%s\n---\n%s\n' "$TOP_LEVEL_DIRS" "$MANIFEST_PATHS" "$DOC_IMPORT_PATHS" "$CONFIG_PATHS" "$WORKFLOW_PATHS")")"
capture_markdown_note "history-import" "structural-summary-note" "$EVIDENCE_IMPORTS_DIR/structural-summary.md" "bedrock/Evidence/imports/structural-summary.md" "imports" "import-agent-history.sh" "structural-summary" "EXTRACTED" "$ARCH_SUMMARY_RELATED" "Compact structural evidence note derived from repo surfaces. Evidence only." "$STRUCTURAL_SUMMARY_SIGNATURE" <<EOF
---
note_type: structural-evidence
project: $PROJECT_NAME
profile: ${LIKELY_PROFILE:-unknown}
source: import-agent-history.sh
kind: structural-summary
confidence: EXTRACTED
generated_at: $GENERATED_AT
related_paths:
$(kc_yaml_list "$ARCH_SUMMARY_RELATED" 2)
notes:
  - Generated from manifests, docs, config files, and top-level structure.
  - Treat this as evidence first, not durable memory.
tags:
  - bedrock
  - evidence
  - structural
---

# Structural Evidence Summary

## Purpose

- Quick orientation note derived from direct repository scans.

## Current Signal

- Likely project profile: \`$LIKELY_PROFILE\`
- Top-level directories: $(if [ -n "$TOP_LEVEL_DIRS" ]; then printf '%s' "$TOP_LEVEL_DIRS" | awk 'NF { items[++count]=$0 } END { for (i=1;i<=count;i++) { printf "`%s`", items[i]; if (i < count) printf ", " } }'; else printf 'none detected'; fi)
- Key manifests: $(if [ -n "$MANIFEST_PATHS" ]; then printf '%s' "$MANIFEST_PATHS" | awk 'NF { items[++count]=$0 } END { for (i=1;i<=count;i++) { printf "`%s`", items[i]; if (i < count) printf ", " } }'; else printf 'none detected'; fi)
- Key docs: $(if [ -n "$DOC_IMPORT_PATHS" ]; then printf '%s' "$DOC_IMPORT_PATHS" | awk 'NF { items[++count]=$0 } END { for (i=1;i<=count;i++) { printf "`%s`", items[i]; if (i < count) printf ", " } }'; else printf 'none detected'; fi)

## Related Evidence

- [../raw/structure.txt](../raw/structure.txt)
- [../raw/manifests.txt](../raw/manifests.txt)
- [../raw/config-files.txt](../raw/config-files.txt)
- [existing-docs.txt](existing-docs.txt)
- [doc-index.txt](doc-index.txt)

## Open Questions

- Which structural signals should be promoted into curated memory after review?
- Are there ignored or external paths that materially change the architecture picture?
EOF

OUTPUT_SUMMARY_SIGNATURE="$(kc_signature_from_lines "$(printf '%s\n---\n%s\n---\n%s\n' "$STRUCTURAL_SUMMARY_SIGNATURE" "$LIKELY_PROFILE" "$ARCH_SUMMARY_RELATED")")"
capture_markdown_note "history-import" "architecture-summary-output" "$OUTPUTS_DIR/architecture-summary.md" "bedrock/Outputs/architecture-summary.md" "outputs" "Evidence/imports/structural-summary.md" "architecture-summary" "INFERRED" "$ARCH_SUMMARY_RELATED" "Generated discovery output derived from evidence. Promote to Memory intentionally if it proves durable." "$OUTPUT_SUMMARY_SIGNATURE" <<EOF
---
note_type: generated-output
project: $PROJECT_NAME
profile: ${LIKELY_PROFILE:-unknown}
source: Evidence/imports/structural-summary.md
kind: architecture-summary
confidence: INFERRED
generated_at: $GENERATED_AT
related_paths:
$(kc_yaml_list "$ARCH_SUMMARY_RELATED" 2)
notes:
  - Derived from structural evidence for quick orientation.
  - Not durable project memory unless promoted intentionally.
tags:
  - bedrock
  - outputs
  - structural
---

# Architecture Summary

## Purpose

- Concise orientation note for discovery before deeper grep or file reads.

## Likely Shape

- Inferred profile: \`$LIKELY_PROFILE\`
- Major top-level branches: $(if [ -n "$TOP_LEVEL_DIRS" ]; then printf '%s' "$TOP_LEVEL_DIRS" | awk 'NF { items[++count]=$0 } END { for (i=1;i<=count;i++) { printf "`%s`", items[i]; if (i < count) printf ", " } }'; else printf 'none detected'; fi)
- Validation and delivery surfaces: $(if [ -n "$WORKFLOW_PATHS" ] || [ -n "$TEST_PATHS" ]; then printf '%s\n%s\n' "$WORKFLOW_PATHS" "$TEST_PATHS" | awk 'NF && !seen[$0]++ { items[++count]=$0 } END { for (i=1;i<=count;i++) { printf "`%s`", items[i]; if (i < count) printf ", " } }'; else printf 'none detected'; fi)

## Evidence Sources

- [../Evidence/imports/structural-summary.md](../Evidence/imports/structural-summary.md)
- [../Evidence/raw/structure.txt](../Evidence/raw/structure.txt)
- [../Evidence/raw/manifests.txt](../Evidence/raw/manifests.txt)
- [../Evidence/raw/ci-workflows.txt](../Evidence/raw/ci-workflows.txt)

## Promotion Rule

- Use this note for orientation only.
- Promote a point into \`Memory/\` only after agent review confirms it is durable and useful.
EOF

STRUCTURAL_MAP_SIGNATURE="$(kc_signature_from_lines "$(printf '%s\n---\n%s\n---\n%s\n---\n%s\n' "$TOP_LEVEL_DIRS" "$MANIFEST_PATHS" "$DOC_IMPORT_PATHS" "$TEST_PATHS")")"
capture_markdown_note "history-import" "structural-map-output" "$OUTPUTS_DIR/structural-map.md" "bedrock/Outputs/structural-map.md" "outputs" "Evidence/raw/structure.txt" "structural-map" "EXTRACTED" "$ARCH_SUMMARY_RELATED" "Generated structure map for fast navigation. Evidence/output first, not memory." "$STRUCTURAL_MAP_SIGNATURE" <<EOF
---
note_type: generated-output
project: $PROJECT_NAME
profile: ${LIKELY_PROFILE:-unknown}
source: Evidence/raw/structure.txt
kind: structural-map
confidence: EXTRACTED
generated_at: $GENERATED_AT
related_paths:
$(kc_yaml_list "$ARCH_SUMMARY_RELATED" 2)
notes:
  - Generated from direct path listings and manifest/doc surfaces.
  - Intended for orientation and navigation, not canonical memory.
tags:
  - bedrock
  - outputs
  - structure
---

# Structural Map

## Top-Level Directories

$(if [ -n "$TOP_LEVEL_DIRS" ]; then printf '%s\n' "$TOP_LEVEL_DIRS" | awk 'NF { printf "- `%s`\n", $0 }'; else echo "- None detected."; fi)

## Key Manifests

$(if [ -n "$MANIFEST_PATHS" ]; then printf '%s\n' "$MANIFEST_PATHS" | awk 'NF { printf "- `%s`\n", $0 }'; else echo "- None detected."; fi)

## Key Docs

$(if [ -n "$DOC_IMPORT_PATHS" ]; then printf '%s\n' "$DOC_IMPORT_PATHS" | awk 'NF { printf "- `%s`\n", $0 }'; else echo "- None detected."; fi)

## Test And Workflow Surfaces

$(if [ -n "$TEST_PATHS" ] || [ -n "$WORKFLOW_PATHS" ]; then printf '%s\n%s\n' "$TEST_PATHS" "$WORKFLOW_PATHS" | awk 'NF && !seen[$0]++ { printf "- `%s`\n", $0 }'; else echo "- None detected."; fi)

## See Also

- [../Evidence/raw/structure.txt](../Evidence/raw/structure.txt)
- [../Evidence/imports/structural-summary.md](../Evidence/imports/structural-summary.md)
EOF

kc_status_load
if [ "${DRY_RUN:-0}" -eq 0 ] && [ ${#GENERATED[@]} -gt 0 ]; then
    STATUS_LAST_IMPORT="$(kc_now_utc)"
fi
STATUS_WARNING_LINES="$(printf '%s\n' "${WARNINGS[@]+"${WARNINGS[@]}"}")"
kc_status_write

json_summary="{"
json_summary="$json_summary\"script\":\"import-agent-history\","
json_summary="$json_summary\"project_root\":\"$(kc_json_escape "$TARGET_PROJECT")\","
json_summary="$json_summary\"dry_run\":$(kc_json_bool "$DRY_RUN"),"
json_summary="$json_summary\"raw_files\":$(kc_json_array "${RAW_GENERATED[@]+"${RAW_GENERATED[@]}"}"),"
json_summary="$json_summary\"import_files\":$(kc_json_array "${IMPORT_GENERATED[@]+"${IMPORT_GENERATED[@]}"}"),"
json_summary="$json_summary\"output_files\":$(kc_json_array "${OUTPUT_GENERATED[@]+"${OUTPUT_GENERATED[@]}"}"),"
json_summary="$json_summary\"cached\":$(kc_json_array "${CACHED[@]+"${CACHED[@]}"}"),"
json_summary="$json_summary\"skipped\":$(kc_json_array "${SKIPPED[@]+"${SKIPPED[@]}"}"),"
json_summary="$json_summary\"warnings\":$(kc_json_array "${WARNINGS[@]+"${WARNINGS[@]}"}")"
json_summary="$json_summary}"
kc_write_json_output "$json_summary"

if [ "$JSON_MODE" -ne 1 ]; then
    kc_log ""
    kc_log "Evidence collected in:"
    kc_log "  bedrock/Evidence/raw/"
    kc_log "  bedrock/Evidence/imports/"
    kc_log "Generated discovery outputs:"
    kc_log "  bedrock/Outputs/architecture-summary.md"
    kc_log "  bedrock/Outputs/structural-map.md"
    if [ ${#CACHED[@]} -gt 0 ]; then
        kc_log ""
        kc_log "Cached:"
        printf '  %s\n' "${CACHED[@]+"${CACHED[@]}"}"
    fi
    kc_log ""
    kc_log "Curated memory remains separate. Review evidence before writing durable notes."
fi
