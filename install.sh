#!/usr/bin/env bash
# Install vietsub skill for Cursor, Claude Code, or Antigravity.
# Usage:
#   curl -fsSL .../install.sh | bash
#   curl -fsSL .../install.sh | bash -s -- --tool claude
#   curl -fsSL .../install.sh | bash -s -- --tool cursor,claude
#   ./install.sh --interactive

set -euo pipefail

REPO_URL="${VIETSUB_REPO_URL:-https://github.com/viet241/vietsub-translation-skill.git}"
REPO_BRANCH="${VIETSUB_REPO_BRANCH:-main}"
SKILL_NAME="vietsub"
TOOL=""   # empty = auto-detect or interactive
REINSTALL=0
DETECT_ONLY=0
INTERACTIVE=0

VALID_TOOLS=(cursor claude antigravity antigravity-project)

usage() {
    cat <<'EOF'
vietsub installer

Usage:
  install.sh [options]

Options:
  --tool <names>    cursor | claude | antigravity | antigravity-project
                    comma-separated for multiple (e.g. cursor,claude)
                    omit to auto-detect; use --interactive to pick
  --interactive     Choose tools from a menu (local terminal only)
  --detect          List detected agent tools and exit
  --reinstall       Remove existing folder and clone fresh
  -h, --help        Show this help

Examples:
  curl -fsSL .../install.sh | bash
  curl -fsSL .../install.sh | bash -s -- --tool claude
  curl -fsSL .../install.sh | bash -s -- --tool cursor,claude
  ./install.sh --interactive
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --tool)
            TOOL="${2:?missing value for --tool}"
            shift 2
            ;;
        --interactive)
            INTERACTIVE=1
            shift
            ;;
        --detect)
            DETECT_ONLY=1
            shift
            ;;
        --reinstall)
            REINSTALL=1
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

has_cursor() {
    [[ -d "${HOME}/.cursor" ]] \
        || [[ -d "/Applications/Cursor.app" ]] \
        || [[ -d "${HOME}/Applications/Cursor.app" ]] \
        || command -v cursor >/dev/null 2>&1
}

has_claude() {
    [[ -d "${HOME}/.claude" ]] \
        || command -v claude >/dev/null 2>&1
}

has_antigravity() {
    [[ -d "${HOME}/.gemini/config/skills" ]] \
        || [[ -d "${HOME}/.gemini/config" ]] \
        || [[ -d "${HOME}/.agents/skills" ]]
}

detect_tools() {
    has_cursor && echo "cursor"
    has_claude && echo "claude"
    has_antigravity && echo "antigravity"
}

validate_tool() {
    local name="$1"
    local valid
    for valid in "${VALID_TOOLS[@]}"; do
        [[ "$name" == "$valid" ]] && return 0
    done
    echo "Unknown tool: $name (use cursor | claude | antigravity | antigravity-project)" >&2
    return 1
}

parse_tool_names() {
    local input="$1"
    local part
    local IFS=','
    for part in $input; do
        part="${part// /}"
        [[ -z "$part" ]] && continue
        validate_tool "$part" || exit 1
        echo "$part"
    done
}

dest_for_tool() {
    if [[ -n "${VIETSUB_INSTALL_DIR:-}" && ${#TOOLS[@]} -eq 1 ]]; then
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

invoke_for_tool() {
    case "$1" in
        cursor | claude) echo "/vietsub" ;;
        *) echo "follow SKILL.md or invoke skill" ;;
    esac
}

choose_tools_interactive() {
    local choice part idx picked=()
    local -a options=("${DETECTED[@]}")

    if [[ ${#options[@]} -eq 0 ]]; then
        echo "No agent tools detected. Enter tool names (comma-separated):"
        echo "  cursor | claude | antigravity | antigravity-project"
        read -r -p "> " choice
        while IFS= read -r part; do
            [[ -n "$part" ]] && picked+=("$part")
        done < <(parse_tool_names "$choice")
        TOOLS=("${picked[@]}")
        return 0
    fi

    echo "Chọn tool cần cài:"
    local i=1
    for t in "${options[@]}"; do
        echo "  $i) $t  -> $(dest_for_tool "$t")"
        ((i++)) || true
    done
    echo "  a) tất cả"
    read -r -p "Lựa chọn [a / số / cursor,claude]: " choice

    choice="${choice// /}"
    if [[ -z "$choice" || "$choice" == "a" || "$choice" == "all" ]]; then
        TOOLS=("${options[@]}")
        return 0
    fi

    if [[ "$choice" =~ ^[0-9,]+$ ]]; then
        IFS=',' read -ra nums <<< "$choice"
        for idx in "${nums[@]}"; do
            if [[ "$idx" =~ ^[0-9]+$ ]] && (( idx >= 1 && idx <= ${#options[@]} )); then
                picked+=("${options[$((idx - 1))]}")
            else
                echo "Invalid choice: $idx" >&2
                exit 1
            fi
        done
        TOOLS=("${picked[@]}")
        return 0
    fi

    while IFS= read -r part; do
        [[ -n "$part" ]] && picked+=("$part")
    done < <(parse_tool_names "$choice")
    TOOLS=("${picked[@]}")
}

require_git() {
    if ! command -v git >/dev/null 2>&1; then
        echo "Error: git not found" >&2
        exit 1
    fi
}

require_python() {
    PYTHON=""
    if command -v python3 >/dev/null 2>&1; then
        PYTHON="python3"
    elif command -v python >/dev/null 2>&1; then
        PYTHON="python"
    else
        echo "Error: python3 not found (need Python 3.10+)" >&2
        exit 1
    fi

    if ! "$PYTHON" -m pip --version >/dev/null 2>&1; then
        echo "Error: pip not available for $PYTHON" >&2
        exit 1
    fi
}

DETECTED=()
while IFS= read -r _tool; do
    [[ -n "$_tool" ]] && DETECTED+=("$_tool")
done < <(detect_tools)

if [[ "$DETECT_ONLY" -eq 1 ]]; then
    if [[ ${#DETECTED[@]} -eq 0 ]]; then
        echo "No agent tools detected."
        echo "Hints: ~/.cursor (Cursor), ~/.claude (Claude Code), ~/.gemini/config (Antigravity)"
        echo "You can still install with: --tool cursor"
        exit 1
    fi
    echo "Detected agent tools:"
    for t in "${DETECTED[@]}"; do
        echo "  - $t  -> $(dest_for_tool "$t")"
    done
    exit 0
fi

TOOLS=()
if [[ -n "$TOOL" ]]; then
    while IFS= read -r _tool; do
        [[ -n "$_tool" ]] && TOOLS+=("$_tool")
    done < <(parse_tool_names "$TOOL")
elif [[ "$INTERACTIVE" -eq 1 ]] || { [[ -t 0 ]] && [[ ${#DETECTED[@]} -gt 1 ]]; }; then
    choose_tools_interactive
elif [[ ${#DETECTED[@]} -gt 0 ]]; then
    TOOLS=("${DETECTED[@]}")
fi

if [[ ${#TOOLS[@]} -eq 0 ]]; then
    cat >&2 <<'EOF'
No install target selected.

Examples:
  curl -fsSL .../install.sh | bash
  curl -fsSL .../install.sh | bash -s -- --tool claude
  curl -fsSL .../install.sh | bash -s -- --tool cursor,claude
  ./install.sh --interactive

Run ./install.sh --detect to list detected tools.
EOF
    exit 1
fi

require_git
require_python

if [[ -z "$TOOL" && "$INTERACTIVE" -eq 0 ]]; then
    echo "Installing for: ${TOOLS[*]}"
fi

INSTALLED=()

install_for_tool() {
    local tool="$1"
    local dest invoke parent
    dest="$(dest_for_tool "$tool")"
    invoke="$(invoke_for_tool "$tool")"
    parent="$(dirname "$dest")"

    echo ""
    echo "==> Installing for $tool"

    mkdir -p "$parent"

    if [[ -d "$dest" ]]; then
        if [[ "$REINSTALL" -eq 1 ]]; then
            echo "Removing $dest ..."
            rm -rf "$dest"
        elif [[ -d "$dest/.git" ]]; then
            echo "Updating $dest ..."
            git -C "$dest" fetch origin "$REPO_BRANCH"
            git -C "$dest" checkout "$REPO_BRANCH"
            git -C "$dest" pull --ff-only origin "$REPO_BRANCH"
            INSTALLED+=("$tool|$dest|$invoke")
            return 0
        else
            echo "Error: $dest exists and is not a git repo. Use --reinstall." >&2
            exit 1
        fi
    fi

    echo "Cloning $REPO_URL -> $dest"
    git clone --branch "$REPO_BRANCH" --depth 1 "$REPO_URL" "$dest"
    INSTALLED+=("$tool|$dest|$invoke")
}

for t in "${TOOLS[@]}"; do
    install_for_tool "$t"
done

if [[ ${#INSTALLED[@]} -gt 0 ]]; then
    first_dest="${INSTALLED[0]#*|}"
    first_dest="${first_dest%%|*}"
    echo ""
    echo "Installing Python dependencies ..."
    "$PYTHON" -m pip install -r "$first_dest/requirements.txt"
fi

echo ""
echo "Done. vietsub installed for ${#INSTALLED[@]} target(s):"
for entry in "${INSTALLED[@]}"; do
    tool="${entry%%|*}"
    rest="${entry#*|}"
    dest="${rest%%|*}"
    invoke="${rest##*|}"
    echo ""
    echo "  [$tool] $dest"
    echo "    invoke: $invoke"
done
echo ""
echo "Requires Python 3.10+ (dependencies installed via pip)."
