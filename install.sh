#!/usr/bin/env bash
# 用法：./install.sh [claude|codex|agents|all] [--copy] [--dry-run]
#   claude → ~/.claude/skills   开发模式（正式安装用 Claude Code 里的 /plugin marketplace add <本目录>）
#   codex  → $CODEX_HOME/skills（默认 ~/.codex/skills；Codex 用了别的主目录就先 export CODEX_HOME）
#   agents → ~/.agents/skills   DeepSeek Harness 等读这个目录
# all 只装到已经存在的目录；指定单个目标时会创建目录。默认软链接，--copy 复制。
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-all}"; MODE="link"; DRY=""
for a in "${@:2}"; do case "$a" in --copy) MODE="copy";; --dry-run) DRY=1;; esac; done
case "$TARGET" in
  claude) dests=("$HOME/.claude/skills"); CREATE=1;;
  codex)  dests=("${CODEX_HOME:-$HOME/.codex}/skills");  CREATE=1;;
  agents) dests=("$HOME/.agents/skills"); CREATE=1;;
  all)    dests=("$HOME/.claude/skills" "${CODEX_HOME:-$HOME/.codex}/skills" "$HOME/.agents/skills"); CREATE="";;
  *) echo "unknown target: $TARGET" >&2; exit 2;;
esac
for d in "${dests[@]}"; do
  if [ ! -d "$d" ]; then
    if [ -n "$CREATE" ] && [ -z "$DRY" ]; then mkdir -p "$d"; else echo "skip (no such dir): $d"; continue; fi
  fi
  for s in "$HERE"/skills/*/; do
    name="$(basename "$s")"; dst="$d/$name"
    if [ -n "$DRY" ]; then echo "would $MODE ${s%/} -> $dst"; continue; fi
    if [ -e "$dst" ] && [ ! -L "$dst" ]; then echo "skip (exists, not a link): $dst"; continue; fi
    rm -rf "$dst"
    if [ "$MODE" = copy ]; then cp -R "${s%/}" "$dst"; else ln -s "${s%/}" "$dst"; fi
    echo "$MODE: $dst"
  done
done
echo "campus-apply $(cat "$HERE/skills/campus-apply/VERSION")；更新时重新拉仓库再跑一遍本脚本。"
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) echo "Windows 提示：终端先执行 chcp 65001，读 SKILL.md 时按 UTF-8，否则中文会乱码。";; esac
