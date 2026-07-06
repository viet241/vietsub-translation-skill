#!/usr/bin/env bash
# Uninstall vietsub skill from Cursor, Claude Code, or Antigravity.
# Usage:
#   ./uninstall.sh --dry-run
#   ./uninstall.sh --yes
#   curl -fsSL .../uninstall.sh | bash -s -- --yes

set -euo pipefail

SKILL_NAME="vietsub"
TOOL=""
YES=0
DRY_RUN=0
DETECT_ONLY=0

usage() {
    cat <<'EOF'
vietsub uninstaller

Usage:
  uninstall.sh [options]

Options:
  --tool <names>    cursor | claude | antigravity | antigravity-project
                    comma-separated for multiple (e.g. cursor,claude)
  --detect          List installed vietsub paths and exit
  --dry-run         Show what would be removed (no changes)
  --yes             Confirm removal (required to delete)
  -h, --help        Show this help

Examples:
  ./uninstall.sh --detect
  ./uninstall.sh --dry-run
  ./uninstall.sh --yes
  ./uninstall.sh --tool cursor,claude --yes
EOF
}

parse_tool_names() {
    local input="$1"
    local part
    local IFS=','
    for part in $input; do
        part="${part// /}"
        [[ -z "$part" ]] && continue
        case "$part" in
            cursor | claude | antigravity | antigravity-project) echo "$part" ;;
            *)
                echo "Unknown tool: $part" >&2
                return 1
                ;;
        esac
    done
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --tool)
            TOOL="${2:?missing value for --tool}"
            shift 2
            ;;
        --detect)
            DETECT_ONLY=1
            shift
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --yes)
            YES=1
            shift
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [[ -z "$TOOL" && -n "${VIETSUB_TOOL:-}" ]]; then
    TOOL="$VIETSUB_TOOL"
fi

dest_for_tool() {
    if [[ -n "${VIETSUB_INSTALL_DIR:-}" ]]; then
        echo "$VIETSUB_INSTALL_DIR"
        return 0
    fi
    case "$1" in
        cursor) echo "$HOME/.cursor/skills/$SKILL_NAME" ;;
        claude) echo "$HOME/.claude/skills/$SKILL_NAME" ;;
        antigravity) echo "$HOME/.gemini/config/skills/$SKILL_NAME" ;;
        antigravity-project) echo "$(pwd)/.agents/skills/$SKILL_NAME" ;;
        *)
            echo "Unknown tool: $1" >&2
            return 1
            ;;
    esac
}

is_vietsub_install() {
    local dest="$1"
    [[ -d "$dest" && -f "$dest/SKILL.md" ]]
}

list_targets() {
    local tool dest
    if [[ -n "$TOOL" ]]; then
        while IFS= read -r tool; do
            [[ -z "$tool" ]] && continue
            dest="$(dest_for_tool "$tool")"
            if is_vietsub_install "$dest"; then
                echo "$tool|$dest"
            fi
        done < <(parse_tool_names "$TOOL")
        return 0
    fi

    for tool in cursor claude antigravity antigravity-project; do
        dest="$(dest_for_tool "$tool")"
        if is_vietsub_install "$dest"; then
            echo "$tool|$dest"
        fi
    done
}

TARGETS=()
while IFS= read -r _line; do
    [[ -n "$_line" ]] && TARGETS+=("$_line")
done < <(list_targets)

if [[ "$DETECT_ONLY" -eq 1 || "$DRY_RUN" -eq 1 ]]; then
    if [[ ${#TARGETS[@]} -eq 0 ]]; then
        echo "No vietsub install found."
        exit 0
    fi
    if [[ "$DETECT_ONLY" -eq 1 ]]; then
        echo "Installed vietsub skill:"
    else
        echo "Would remove:"
    fi
    for entry in "${TARGETS[@]}"; do
        tool="${entry%%|*}"
        dest="${entry#*|}"
        echo "  - [$tool] $dest"
    done
    exit 0
fi

if [[ ${#TARGETS[@]} -eq 0 ]]; then
    echo "No vietsub install found — nothing to remove."
    exit 0
fi

if [[ "$YES" -ne 1 ]]; then
    cat <<'EOF'
Refusing to remove without --yes.

Preview installed paths:
EOF
    for entry in "${TARGETS[@]}"; do
        tool="${entry%%|*}"
        dest="${entry#*|}"
        echo "  - [$tool] $dest"
    done
    echo ""
    echo "Re-run with --yes to uninstall, or use --dry-run to preview."
    exit 1
fi

for entry in "${TARGETS[@]}"; do
    tool="${entry%%|*}"
    dest="${entry#*|}"
    echo "Removing [$tool] $dest ..."
    rm -rf "$dest"
done

echo ""
echo "Done. Removed ${#TARGETS[@]} vietsub install(s)."
echo "Note: Python packages (pysubs2, chardet, …) are not removed."
echo "Job folders (e.g. movie_batches/) are not removed — delete those manually if needed."
