#!/bin/bash

# Shared helpers for the operational knowledge scripts.
# Bash 3 compatible.

DRY_RUN="${DRY_RUN:-0}"
JSON_MODE="${JSON_MODE:-0}"
FORCE="${FORCE:-0}"
SUMMARY_FILE="${SUMMARY_FILE:-}"
SHOW_HELP="${SHOW_HELP:-0}"

KC_LAST_ACTION=""
KC_CHILD_SUMMARY=""

kc_now_utc() {
    date -u +"%Y-%m-%dT%H:%M:%SZ"
}

kc_today() {
    date +"%Y-%m-%d"
}

kc_log() {
    if [ "${JSON_MODE:-0}" -ne 1 ]; then
        printf '%s\n' "$*"
    fi
}

kc_err() {
    printf '%s\n' "$*" >&2
}

kc_fail() {
    kc_err "$*"
    exit 1
}

kc_parse_common_flag() {
    case "${1:-}" in
        --dry-run)
            DRY_RUN=1
            return 0
            ;;
        --json)
            JSON_MODE=1
            return 0
            ;;
        --summary-file)
            SUMMARY_FILE="${2:-}"
            return 2
            ;;
        --force)
            FORCE=1
            return 0
            ;;
        --help|-h)
            SHOW_HELP=1
            return 0
            ;;
    esac
    return 1
}

kc_json_escape() {
    local value="${1:-}"
    value=${value//\\/\\\\}
    value=${value//\"/\\\"}
    value=${value//$'\n'/\\n}
    value=${value//$'\r'/\\r}
    value=${value//$'\t'/\\t}
    printf '%s' "$value"
}

kc_json_bool() {
    if [ "${1:-0}" -eq 1 ] 2>/dev/null; then
        printf 'true'
    else
        printf 'false'
    fi
}

kc_json_array() {
    local first=1
    local item=""
    printf '['
    for item in "$@"; do
        if [ $first -eq 0 ]; then
            printf ','
        fi
        first=0
        printf '"%s"' "$(kc_json_escape "$item")"
    done
    printf ']'
}

kc_json_array_from_lines() {
    local text="${1:-}"
    local items=()
    local line=""

    while IFS= read -r line; do
        [ -n "$line" ] || continue
        items+=("$line")
    done <<EOF
$text
EOF

    kc_json_array "${items[@]+"${items[@]}"}"
}

kc_write_json_output() {
    local json="$1"

    if [ -n "${SUMMARY_FILE:-}" ]; then
        printf '%s\n' "$json" > "$SUMMARY_FILE"
    fi

    if [ "${JSON_MODE:-0}" -eq 1 ]; then
        printf '%s\n' "$json"
    fi
}

kc_run_child_script() {
    local script="$1"
    shift
    local tmp_file=""
    local exit_code=0

    KC_CHILD_SUMMARY=""

    if [ "${JSON_MODE:-0}" -eq 1 ]; then
        tmp_file="$(mktemp)"
        if ! "$script" "$@" --json --summary-file "$tmp_file" >/dev/null; then
            exit_code=$?
        fi
        if [ -f "$tmp_file" ]; then
            KC_CHILD_SUMMARY="$(cat "$tmp_file" 2>/dev/null || true)"
            rm -f "$tmp_file"
        fi
        return "$exit_code"
    fi

    "$script" "$@"
}

kc_resolve_relative() {
    local base="$1"
    local path_value="$2"

    case "$path_value" in
        "")
            return 1
            ;;
        /*)
            printf '%s\n' "$path_value"
            ;;
        ~/*)
            printf '%s\n' "$HOME/${path_value#~/}"
            ;;
        *)
            (
                cd "$base" 2>/dev/null && printf '%s/%s\n' "$(pwd)" "$path_value"
            )
            ;;
    esac
}

kc_yaml_leaf_value() {
    local file="$1"
    local key="$2"

    awk -v key="$key" '
        $0 ~ "^[[:space:]]*" key ":[[:space:]]*" {
            value = $0
            sub("^[[:space:]]*" key ":[[:space:]]*", "", value)
            gsub(/^["'"'"']|["'"'"']$/, "", value)
            print value
            exit
        }
    ' "$file" 2>/dev/null
}

kc_slugify() {
    printf '%s' "$1" \
        | tr '[:upper:]' '[:lower:]' \
        | sed 's/[^a-z0-9]/-/g' \
        | sed 's/-\{2,\}/-/g' \
        | sed 's/^-//' \
        | sed 's/-$//'
}

kc_ensure_dir() {
    local dir="$1"
    local label="${2:-$1}"

    if [ -d "$dir" ]; then
        KC_LAST_ACTION="unchanged"
        return 0
    fi

    if [ "${DRY_RUN:-0}" -eq 1 ]; then
        kc_log "  would create dir: $label"
        KC_LAST_ACTION="would-create"
        return 0
    fi

    mkdir -p "$dir"
    kc_log "  created dir: $label"
    KC_LAST_ACTION="created"
}

kc_apply_temp_file() {
    local tmp_file="$1"
    local dst="$2"
    local label="${3:-$2}"
    local existed=0

    if [ -e "$dst" ]; then
        existed=1
    fi

    if [ "$existed" -eq 1 ] && cmp -s "$tmp_file" "$dst"; then
        rm -f "$tmp_file"
        KC_LAST_ACTION="unchanged"
        return 0
    fi

    if [ "${DRY_RUN:-0}" -eq 1 ]; then
        if [ "$existed" -eq 1 ]; then
            kc_log "  would update: $label"
            KC_LAST_ACTION="would-update"
        else
            kc_log "  would create: $label"
            KC_LAST_ACTION="would-create"
        fi
        rm -f "$tmp_file"
        return 0
    fi

    mkdir -p "$(dirname "$dst")"
    cp "$tmp_file" "$dst"
    rm -f "$tmp_file"

    if [ "$existed" -eq 1 ]; then
        kc_log "  updated: $label"
        KC_LAST_ACTION="updated"
    else
        kc_log "  created: $label"
        KC_LAST_ACTION="created"
    fi
}

kc_write_text_file() {
    local dst="$1"
    local label="${2:-$1}"
    local tmp_file

    tmp_file="$(mktemp)"
    cat > "$tmp_file"
    kc_apply_temp_file "$tmp_file" "$dst" "$label"
}

kc_copy_file() {
    local src="$1"
    local dst="$2"
    local label="${3:-$2}"
    local tmp_file

    tmp_file="$(mktemp)"
    cat "$src" > "$tmp_file"
    kc_apply_temp_file "$tmp_file" "$dst" "$label"
}

kc_replace_in_template() {
    local src="$1"
    local dst="$2"
    local label="$3"
    shift 3

    local tmp_file
    local expr=()
    local pair=""
    local key=""
    local value=""

    tmp_file="$(mktemp)"
    while [ "$#" -gt 1 ]; do
        key="$1"
        value="$2"
        expr+=("-e" "s|$key|$value|g")
        shift 2
    done

    sed "${expr[@]}" "$src" > "$tmp_file"
    kc_apply_temp_file "$tmp_file" "$dst" "$label"
}

kc_ensure_symlink() {
    local target="$1"
    local link_path="$2"
    local label="${3:-$2}"
    local current_target=""

    if [ -L "$link_path" ]; then
        current_target="$(readlink "$link_path" 2>/dev/null || true)"
        if [ "$current_target" = "$target" ]; then
            KC_LAST_ACTION="unchanged"
            return 0
        fi
    elif [ -e "$link_path" ]; then
        kc_fail "Refusing to replace non-symlink path: $link_path"
    fi

    if [ "${DRY_RUN:-0}" -eq 1 ]; then
        kc_log "  would link: $label -> $target"
        if [ -L "$link_path" ]; then
            KC_LAST_ACTION="would-update"
        else
            KC_LAST_ACTION="would-create"
        fi
        return 0
    fi

    mkdir -p "$(dirname "$link_path")"
    ln -sfn "$target" "$link_path"
    kc_log "  linked: $label -> $target"
    if [ -L "$link_path" ]; then
        KC_LAST_ACTION="updated"
    else
        KC_LAST_ACTION="created"
    fi
}

kc_detect_symlink_caveat() {
    case "$(uname -s 2>/dev/null || echo unknown)" in
        MINGW*|MSYS*|CYGWIN*)
            printf '%s\n' "Windows environments may require Developer Mode or administrator rights for symlinks. If link creation fails, use a junction or run the shell with elevated permissions."
            ;;
        *)
            printf '%s\n' ""
            ;;
    esac
}

kc_load_project_context() {
    local project_dir="${1:-.}"
    local pointer_value=""
    local real_value=""

    TARGET_PROJECT="$(cd "$project_dir" 2>/dev/null && pwd)"
    [ -n "$TARGET_PROJECT" ] || kc_fail "Unable to resolve project dir: $project_dir"

    PROJECT_NAME="$(basename "$TARGET_PROJECT")"
    PROJECT_SLUG="$(kc_slugify "$PROJECT_NAME")"
    PROJECT_PROFILE="unknown"
    VAULT_MODE="external"
    AGENT_PROJECT_FILE="$TARGET_PROJECT/.agent-project.yaml"
    POINTER_PATH="$TARGET_PROJECT/agent-knowledge"
    POINTER_DISPLAY="./agent-knowledge"
    FRAMEWORK_REPO=""

    if [ -f "$AGENT_PROJECT_FILE" ]; then
        PROJECT_NAME="$(kc_yaml_leaf_value "$AGENT_PROJECT_FILE" "name" || printf '%s' "$PROJECT_NAME")"
        PROJECT_SLUG="$(kc_yaml_leaf_value "$AGENT_PROJECT_FILE" "slug" || printf '%s' "$PROJECT_SLUG")"
        PROJECT_PROFILE="$(kc_yaml_leaf_value "$AGENT_PROJECT_FILE" "profile_hint" || kc_yaml_leaf_value "$AGENT_PROJECT_FILE" "profile" || printf 'unknown')"
        FRAMEWORK_REPO="$(kc_yaml_leaf_value "$AGENT_PROJECT_FILE" "repo" || true)"
        VAULT_MODE="$(kc_yaml_leaf_value "$AGENT_PROJECT_FILE" "vault_mode" 2>/dev/null || printf 'external')"
        pointer_value="$(kc_yaml_leaf_value "$AGENT_PROJECT_FILE" "pointer_path" || true)"
        real_value="$(kc_yaml_leaf_value "$AGENT_PROJECT_FILE" "real_path" || true)"
        if [ -n "$pointer_value" ]; then
            POINTER_DISPLAY="$pointer_value"
            POINTER_PATH="$(kc_resolve_relative "$TARGET_PROJECT" "$pointer_value")"
        fi
    fi

    if [ -n "$real_value" ]; then
        KNOWLEDGE_REAL_DIR="$(kc_resolve_relative "$TARGET_PROJECT" "$real_value")"
        if [ -d "$KNOWLEDGE_REAL_DIR" ]; then
            KNOWLEDGE_REAL_DIR="$(cd "$KNOWLEDGE_REAL_DIR" 2>/dev/null && pwd -P)"
        fi
    elif [ -d "$POINTER_PATH" ]; then
        KNOWLEDGE_REAL_DIR="$(cd "$POINTER_PATH" 2>/dev/null && pwd -P)"
    else
        KNOWLEDGE_REAL_DIR="$POINTER_PATH"
    fi

    KNOWLEDGE_POINTER_PATH="$POINTER_PATH"
    KNOWLEDGE_DIR="$POINTER_PATH"
    MEMORY_DIR="$KNOWLEDGE_DIR/Memory"
    MEMORY_ROOT="$MEMORY_DIR/MEMORY.md"
    DECISIONS_DIR="$MEMORY_DIR/decisions"
    EVIDENCE_DIR="$KNOWLEDGE_DIR/Evidence"
    EVIDENCE_RAW_DIR="$EVIDENCE_DIR/raw"
    EVIDENCE_IMPORTS_DIR="$EVIDENCE_DIR/imports"
    EVIDENCE_TOOLING_DIR="$EVIDENCE_DIR/tooling"
    OUTPUTS_DIR="$KNOWLEDGE_DIR/Outputs"
    DASHBOARDS_DIR="$KNOWLEDGE_DIR/Dashboards"
    LOCAL_TEMPLATES_DIR="$KNOWLEDGE_DIR/Templates"
    OBSIDIAN_DIR="$KNOWLEDGE_DIR/.obsidian"
    STATUS_FILE="$KNOWLEDGE_DIR/STATUS.md"
    KNOWLEDGE_CACHE_DIR="$KNOWLEDGE_DIR/.cache"
    EVIDENCE_CACHE_DIR="$EVIDENCE_DIR/.cache"
    IGNORE_FILE="$TARGET_PROJECT/.agentknowledgeignore"
    KC_IGNORE_PATTERNS=()
    if [ -f "$IGNORE_FILE" ]; then
        while IFS= read -r pattern; do
            pattern="${pattern%$'\r'}"
            case "$pattern" in
                ""|\#*)
                    continue
                    ;;
            esac
            KC_IGNORE_PATTERNS+=("$pattern")
        done < "$IGNORE_FILE"
    fi
}

kc_is_windows_like() {
    case "$(uname -s 2>/dev/null || echo unknown)" in
        MINGW*|MSYS*|CYGWIN*)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

kc_pointer_resolved_path() {
    [ -d "$KNOWLEDGE_POINTER_PATH" ] || return 1
    (
        cd "$KNOWLEDGE_POINTER_PATH" 2>/dev/null && pwd -P
    )
}

kc_rel_knowledge_path() {
    local path="$1"

    case "$path" in
        "$KNOWLEDGE_DIR"/*)
            printf '%s\n' "${path#$KNOWLEDGE_DIR/}"
            ;;
        "$KNOWLEDGE_REAL_DIR"/*)
            printf '%s\n' "${path#$KNOWLEDGE_REAL_DIR/}"
            ;;
        *)
            printf '%s\n' "$path"
            ;;
    esac
}

kc_normalize_relative_path() {
    local path="${1:-}"
    path="${path#./}"
    path="${path#/}"
    printf '%s\n' "$path"
}

kc_path_is_ignored() {
    local path=""
    local pattern=""
    local normalized_pattern=""
    local base=""

    path="$(kc_normalize_relative_path "${1:-}")"
    [ -n "$path" ] || return 1

    for pattern in "${KC_IGNORE_PATTERNS[@]+"${KC_IGNORE_PATTERNS[@]}"}"; do
        normalized_pattern="$(kc_normalize_relative_path "$pattern")"
        [ -n "$normalized_pattern" ] || continue
        case "$normalized_pattern" in
            */)
                base="${normalized_pattern%/}"
                case "$path" in
                    $base|$base/*)
                        return 0
                        ;;
                esac
                ;;
            *)
                case "$path" in
                    $normalized_pattern|$normalized_pattern/*)
                        return 0
                        ;;
                esac
                ;;
        esac
    done
    return 1
}

kc_filter_relative_lines() {
    local line=""
    local normalized=""

    while IFS= read -r line; do
        [ -n "$line" ] || continue
        normalized="$(kc_normalize_relative_path "$line")"
        if kc_path_is_ignored "$normalized"; then
            continue
        fi
        printf '%s\n' "$normalized"
    done
}

kc_hash_text() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 | awk '{print $1}'
    else
        openssl dgst -sha256 | awk '{print $NF}'
    fi
}

kc_stat_signature_line() {
    local path="$1"
    local label="${2:-$1}"
    local meta=""

    if stat -f '%m|%z' "$path" >/dev/null 2>&1; then
        meta="$(stat -f '%m|%z' "$path" 2>/dev/null)"
    else
        meta="$(stat -c '%Y|%s' "$path" 2>/dev/null)"
    fi
    printf '%s|%s\n' "$label" "$meta"
}

kc_signature_from_lines() {
    local text="${1:-}"
    printf '%s' "$text" | kc_hash_text
}

kc_signature_from_paths() {
    local line=""
    local text=""

    for line in "$@"; do
        [ -n "$line" ] || continue
        if [ -e "$line" ]; then
            text="${text}$(kc_stat_signature_line "$line")"$'\n'
        else
            text="${text}missing|$line"$'\n'
        fi
    done

    kc_signature_from_lines "$text"
}

kc_signature_from_project_relative_lines() {
    local relpaths_text="${1:-}"
    local line=""
    local abs=""
    local text=""

    while IFS= read -r line; do
        [ -n "$line" ] || continue
        abs="$TARGET_PROJECT/$(kc_normalize_relative_path "$line")"
        if [ -e "$abs" ]; then
            text="${text}$(kc_stat_signature_line "$abs" "$line")"$'\n'
        else
            text="${text}missing|$line"$'\n'
        fi
    done <<EOF
$relpaths_text
EOF

    if [ -f "$IGNORE_FILE" ]; then
        text="${text}$(kc_stat_signature_line "$IGNORE_FILE" ".agentknowledgeignore")"$'\n'
    fi

    kc_signature_from_lines "$text"
}

kc_cache_key_name() {
    printf '%s' "$1" | sed 's/[^A-Za-z0-9._-]/_/g'
}

kc_cache_signature_path() {
    local namespace="$1"
    local key="$2"
    printf '%s/%s/%s.sig\n' "$KNOWLEDGE_CACHE_DIR" "$(kc_cache_key_name "$namespace")" "$(kc_cache_key_name "$key")"
}

kc_cache_is_current() {
    local namespace="$1"
    local key="$2"
    local signature="$3"
    local cache_path=""
    local current=""
    shift 3

    cache_path="$(kc_cache_signature_path "$namespace" "$key")"
    [ -f "$cache_path" ] || return 1
    current="$(cat "$cache_path" 2>/dev/null || true)"
    [ "$current" = "$signature" ] || return 1

    for current in "$@"; do
        [ -e "$current" ] || return 1
    done
    return 0
}

kc_cache_store() {
    local namespace="$1"
    local key="$2"
    local signature="$3"
    local dst

    dst="$(kc_cache_signature_path "$namespace" "$key")"
    kc_write_text_file "$dst" ".cache/$(kc_cache_key_name "$namespace")/$(kc_cache_key_name "$key").sig" <<EOF
$signature
EOF
}

kc_write_metadata_json() {
    local dst="$1"
    local label="$2"
    local source="$3"
    local kind="$4"
    local confidence="$5"
    local generated_at="$6"
    local related_paths_text="${7:-}"
    local notes_text="${8:-}"
    local tmp_file

    tmp_file="$(mktemp)"
    {
        printf '{'
        printf '"source":"%s",' "$(kc_json_escape "$source")"
        printf '"kind":"%s",' "$(kc_json_escape "$kind")"
        printf '"confidence":"%s",' "$(kc_json_escape "$confidence")"
        printf '"generated_at":"%s",' "$(kc_json_escape "$generated_at")"
        printf '"related_paths":%s,' "$(kc_json_array_from_lines "$related_paths_text")"
        printf '"notes":%s' "$(kc_json_array_from_lines "$notes_text")"
        printf '}\n'
    } > "$tmp_file"

    kc_apply_temp_file "$tmp_file" "$dst" "$label"
}

kc_yaml_list() {
    local text="${1:-}"
    local indent="${2:-2}"
    local line=""
    local prefix=""
    local i=0

    while [ "$i" -lt "$indent" ]; do
        prefix="${prefix} "
        i=$((i + 1))
    done

    while IFS= read -r line; do
        [ -n "$line" ] || continue
        printf '%s- %s\n' "$prefix" "$line"
    done <<EOF
$text
EOF
}

kc_require_project_metadata() {
    [ -f "$AGENT_PROJECT_FILE" ] || kc_fail "Missing $AGENT_PROJECT_FILE"
}

kc_require_knowledge_pointer() {
    [ -e "$KNOWLEDGE_POINTER_PATH" ] || kc_fail "Missing local knowledge pointer: $KNOWLEDGE_POINTER_PATH"
    [ -d "$KNOWLEDGE_POINTER_PATH" ] || kc_fail "Local knowledge pointer is not a directory: $KNOWLEDGE_POINTER_PATH"
    pointer_resolved="$(kc_pointer_resolved_path || true)"
    [ -n "$pointer_resolved" ] || kc_fail "Unable to resolve local knowledge pointer: $KNOWLEDGE_POINTER_PATH"
    [ "$pointer_resolved" = "$KNOWLEDGE_REAL_DIR" ] || kc_fail "Local knowledge pointer must resolve to the external knowledge folder: $KNOWLEDGE_REAL_DIR"
    if [ ! -L "$KNOWLEDGE_POINTER_PATH" ] && ! kc_is_windows_like; then
        kc_fail "Local knowledge handle must be a symlink to the external knowledge folder, not a repo-local directory: $KNOWLEDGE_POINTER_PATH"
    fi
}

kc_git_available() {
    git -C "$TARGET_PROJECT" rev-parse --git-dir >/dev/null 2>&1
}

kc_git_has_commits() {
    git -C "$TARGET_PROJECT" rev-parse --verify HEAD >/dev/null 2>&1
}

kc_git_changed_files() {
    if ! kc_git_available; then
        return 0
    fi

    git -C "$TARGET_PROJECT" status --porcelain 2>/dev/null \
        | sed 's/^...//' \
        | sed 's/ -> /\n/' \
        | awk 'NF { print $0 }' \
        | sort -u
}

kc_append_unique_bullet() {
    local file="$1"
    local section="$2"
    local bullet="$3"
    local label="${4:-$file}"
    local tmp_file

    [ -f "$file" ] || return 1

    tmp_file="$(mktemp)"
    awk -v heading="## $section" -v bullet="$bullet" '
        BEGIN {
            in_section = 0
            seen = 0
            inserted = 0
        }
        {
            if (in_section && /^## / && $0 != heading) {
                if (!seen && !inserted) {
                    print bullet
                    inserted = 1
                }
                in_section = 0
            }

            if ($0 == heading) {
                in_section = 1
            }

            if (in_section && $0 == bullet) {
                seen = 1
            }

            print
        }
        END {
            if (in_section && !seen && !inserted) {
                print bullet
            }
        }
    ' "$file" > "$tmp_file"

    kc_apply_temp_file "$tmp_file" "$file" "$label"
}

kc_has_frontmatter() {
    local file="$1"
    head -1 "$file" 2>/dev/null | grep -q '^---$'
}

kc_status_load() {
    STATUS_PROJECT="$PROJECT_NAME"
    STATUS_PROFILE="$PROJECT_PROFILE"
    STATUS_ONTOLOGY_MODEL="2"
    STATUS_REAL_PATH="$KNOWLEDGE_REAL_DIR"
    STATUS_POINTER_PATH="$POINTER_DISPLAY"
    STATUS_LAST_BOOTSTRAP=""
    STATUS_LAST_IMPORT=""
    STATUS_LAST_PROJECT_SYNC=""
    STATUS_LAST_COMPACTION=""
    STATUS_LAST_VALIDATION=""
    STATUS_LAST_VALIDATION_RESULT="unknown"
    STATUS_LAST_DOCTOR=""
    STATUS_LAST_DOCTOR_RESULT="unknown"
    STATUS_ONBOARDING="pending"
    STATUS_WARNING_LINES=""

    if [ ! -f "$STATUS_FILE" ]; then
        return 0
    fi

    STATUS_PROJECT="$(kc_yaml_leaf_value "$STATUS_FILE" "project" || printf '%s' "$STATUS_PROJECT")"
    # Read profile_hint first, fall back to legacy profile key
    STATUS_PROFILE="$(kc_yaml_leaf_value "$STATUS_FILE" "profile_hint" || kc_yaml_leaf_value "$STATUS_FILE" "profile" || printf '%s' "$STATUS_PROFILE")"
    STATUS_ONTOLOGY_MODEL="$(kc_yaml_leaf_value "$STATUS_FILE" "ontology_model" || printf '2')"
    STATUS_REAL_PATH="$(kc_yaml_leaf_value "$STATUS_FILE" "real_knowledge_path" || printf '%s' "$STATUS_REAL_PATH")"
    STATUS_POINTER_PATH="$(kc_yaml_leaf_value "$STATUS_FILE" "local_pointer_path" || printf '%s' "$STATUS_POINTER_PATH")"
    STATUS_ONBOARDING="$(kc_yaml_leaf_value "$STATUS_FILE" "onboarding" || printf 'pending')"
    STATUS_LAST_BOOTSTRAP="$(kc_yaml_leaf_value "$STATUS_FILE" "last_bootstrap" || true)"
    STATUS_LAST_IMPORT="$(kc_yaml_leaf_value "$STATUS_FILE" "last_backfill_import" || true)"
    STATUS_LAST_PROJECT_SYNC="$(kc_yaml_leaf_value "$STATUS_FILE" "last_project_sync" || true)"
    STATUS_LAST_COMPACTION="$(kc_yaml_leaf_value "$STATUS_FILE" "last_compaction" || true)"
    STATUS_LAST_VALIDATION="$(kc_yaml_leaf_value "$STATUS_FILE" "last_validation" || true)"
    STATUS_LAST_VALIDATION_RESULT="$(kc_yaml_leaf_value "$STATUS_FILE" "last_validation_result" || printf 'unknown')"
    STATUS_LAST_DOCTOR="$(kc_yaml_leaf_value "$STATUS_FILE" "last_doctor" || true)"
    STATUS_LAST_DOCTOR_RESULT="$(kc_yaml_leaf_value "$STATUS_FILE" "last_doctor_result" || printf 'unknown')"
    STATUS_WARNING_LINES="$(
        awk '
            $0 == "## Health Warnings" { in_section = 1; next }
            in_section && /^## / { exit }
            in_section && /^- / { sub(/^- /, "", $0); print }
        ' "$STATUS_FILE" 2>/dev/null
    )"
}

kc_status_write() {
    local tmp_file
    local warnings_text="${1:-$STATUS_WARNING_LINES}"
    local warning=""

    tmp_file="$(mktemp)"
    {
        printf '%s\n' '---'
        printf 'note_type: knowledge-status\n'
        printf 'project: %s\n' "$STATUS_PROJECT"
        printf 'profile_hint: %s\n' "$STATUS_PROFILE"
        printf 'ontology_model: %s\n' "${STATUS_ONTOLOGY_MODEL:-2}"
        printf 'real_knowledge_path: %s\n' "$STATUS_REAL_PATH"
        printf 'local_pointer_path: %s\n' "$STATUS_POINTER_PATH"
        printf 'onboarding: %s\n' "$STATUS_ONBOARDING"
        printf 'last_bootstrap: %s\n' "$STATUS_LAST_BOOTSTRAP"
        printf 'last_backfill_import: %s\n' "$STATUS_LAST_IMPORT"
        printf 'last_project_sync: %s\n' "$STATUS_LAST_PROJECT_SYNC"
        printf 'last_compaction: %s\n' "$STATUS_LAST_COMPACTION"
        printf 'last_validation: %s\n' "$STATUS_LAST_VALIDATION"
        printf 'last_validation_result: %s\n' "$STATUS_LAST_VALIDATION_RESULT"
        printf 'last_doctor: %s\n' "$STATUS_LAST_DOCTOR"
        printf 'last_doctor_result: %s\n' "$STATUS_LAST_DOCTOR_RESULT"
        printf '%s\n\n' '---'
        printf '# Knowledge Status: %s\n\n' "$STATUS_PROJECT"
        printf '## Current State\n\n'
        printf -- '- Profile hint: `%s`\n' "$STATUS_PROFILE"
        printf -- '- Ontology model: `%s`\n' "${STATUS_ONTOLOGY_MODEL:-2}"
        printf -- '- Real knowledge path: `%s`\n' "$STATUS_REAL_PATH"
        printf -- '- Local pointer path: `%s`\n' "$STATUS_POINTER_PATH"
        printf -- '- Onboarding: `%s`\n\n' "$STATUS_ONBOARDING"
        printf '## Activity\n\n'
        printf -- '- Last bootstrap: `%s`\n' "${STATUS_LAST_BOOTSTRAP:-not-yet}"
        printf -- '- Last backfill/import: `%s`\n' "${STATUS_LAST_IMPORT:-not-yet}"
        printf -- '- Last project sync: `%s`\n' "${STATUS_LAST_PROJECT_SYNC:-not-yet}"
        printf -- '- Last compaction: `%s`\n' "${STATUS_LAST_COMPACTION:-not-yet}"
        printf -- '- Last validation: `%s` (`%s`)\n' "${STATUS_LAST_VALIDATION:-not-yet}" "${STATUS_LAST_VALIDATION_RESULT:-unknown}"
        printf -- '- Last doctor: `%s` (`%s`)\n\n' "${STATUS_LAST_DOCTOR:-not-yet}" "${STATUS_LAST_DOCTOR_RESULT:-unknown}"
        printf '## Health Warnings\n\n'
        if [ -n "$warnings_text" ]; then
            printf '%s\n' "$warnings_text" | while read -r warning; do
                [ -n "$warning" ] || continue
                printf -- '- %s\n' "$warning"
            done
        else
            printf -- '- None.\n'
        fi
    } > "$tmp_file"

    kc_apply_temp_file "$tmp_file" "$STATUS_FILE" "agent-knowledge/STATUS.md"
}

kc_run_shell_command() {
    local label="$1"
    local command="$2"
    local workdir="${3:-$PWD}"
    local tmp_file

    tmp_file="$(mktemp)"
    KC_COMMAND_OUTPUT=""
    KC_COMMAND_STATUS="skipped"

    if [ "${DRY_RUN:-0}" -eq 1 ]; then
        kc_log "  would run [$label]: $command"
        KC_COMMAND_STATUS="dry-run"
        rm -f "$tmp_file"
        return 0
    fi

    if (cd "$workdir" && bash -lc "$command") > "$tmp_file" 2>&1; then
        KC_COMMAND_STATUS="passed"
    else
        KC_COMMAND_STATUS="failed"
    fi
    KC_COMMAND_OUTPUT="$(cat "$tmp_file")"
    rm -f "$tmp_file"

    return 0
}
