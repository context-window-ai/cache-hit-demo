#!/usr/bin/env bash
# generate_context.sh — context-window-ai/cache-hit-demo
#
# Clones the OpenRouter Python SDK and concatenates all Python source
# files into a single codebase_context.txt for use in the benchmark.
#
# Usage:
#   bash scripts/generate_context.sh
#   bash scripts/generate_context.sh --force   # re-clone even if exists

set -euo pipefail

REPO_URL="https://github.com/OpenRouterTeam/openrouter-python"
REPO_DIR="openrouter-python"
OUTPUT="codebase_context.txt"
FORCE=false

for arg in "$@"; do
  [[ "$arg" == "--force" ]] && FORCE=true
done

# ── Clone or update ───────────────────────────────────────────────────────────

if [[ "$FORCE" == "true" && -d "$REPO_DIR" ]]; then
  echo "🗑  Removing existing clone..."
  rm -rf "$REPO_DIR"
fi

if [[ -d "$REPO_DIR" ]]; then
  echo "📦 Repository already exists — pulling latest..."
  git -C "$REPO_DIR" pull --quiet
else
  echo "📦 Cloning $REPO_URL..."
  git clone --quiet --depth=1 "$REPO_URL"
fi

# ── Concatenate Python files ──────────────────────────────────────────────────

echo "🔗 Concatenating Python source files..."

# Find all .py files, exclude tests and __pycache__, sort for determinism
mapfile -t FILES < <(
  find "$REPO_DIR" -name "*.py" \
    ! -path "*/__pycache__/*" \
    ! -path "*/.git/*" \
    ! -name "conftest.py" \
    | sort
)

FILE_COUNT=${#FILES[@]}

{
  echo "# OpenRouter Python SDK — full source"
  echo "# Generated: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "# Files: $FILE_COUNT"
  echo ""

  for filepath in "${FILES[@]}"; do
    echo ""
    echo "# ===== $filepath ====="
    echo ""
    cat "$filepath"
  done
} > "$OUTPUT"

# ── Summary ───────────────────────────────────────────────────────────────────

CHAR_COUNT=$(wc -c < "$OUTPUT" | tr -d ' ')
LINE_COUNT=$(wc -l < "$OUTPUT" | tr -d ' ')

# Human-friendly size
if command -v numfmt &>/dev/null; then
  SIZE=$(numfmt --to=si "$CHAR_COUNT")
else
  SIZE="${CHAR_COUNT} chars"
fi

echo ""
echo "✅ Done!"
echo "   Files:  $FILE_COUNT .py files"
echo "   Lines:  $LINE_COUNT"
echo "   Size:   $SIZE"
echo "   Output: $OUTPUT"
echo ""
echo "Next: python benchmark.py"
