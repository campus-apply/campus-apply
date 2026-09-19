#!/bin/zsh
# 用法：TAB_MARK=<运行ID>（或 TAB_MATCH=…）read_urls.sh <列表文件> <输出目录> [起始行] [结束行]
# 列表文件每行：id<TAB>url。逐个把认领的标签页导航到 url，等 PACE_MIN–PACE_MAX 秒（默认 1–2，登录后的页面建议 2–4），
# 用 read_page.js 读正文存 <输出目录>/<id>.json；每 GUARD_EVERY（默认 5）个跑一次 guard，遇验证码/跳登录立即停并打印 STOP。
# 读到的页面 URL 不含 id 或正文太短时打印 MISS <id>。结束打印 done 与成功数。
B="$(cd "$(dirname "$0")" && pwd)"
LIST="$1"; OUT="$2"; FROM="${3:-1}"; TO="${4:-999999}"
PMIN="${PACE_MIN:-1}"; PMAX="${PACE_MAX:-2}"; GE="${GUARD_EVERY:-5}"
mkdir -p "$OUT"; n=0; ok=0
GO=$(mktemp "${TMPDIR:-/tmp}/ca_go.XXXXXX.js")
sed -n "${FROM},${TO}p" "$LIST" | while IFS=$'\t' read id url; do
  [ -n "$id" ] || continue
  n=$((n+1))
  echo "location.href='$url'; 'nav'" > "$GO"
  "$B/chrome_exec.sh" "$GO" >/dev/null
  sleep $(( PMIN + RANDOM % (PMAX - PMIN + 1) ))
  "$B/chrome_exec.sh" "$B/read_page.js" > "$OUT/$id.json"
  if python3 -c "import json,sys;d=json.load(open('$OUT/$id.json'));assert '$id' in d['url'] and len(d['text'])>200" 2>/dev/null; then ok=$((ok+1)); else echo "MISS $id"; fi
  if [ $((n % GE)) -eq 0 ]; then
    g=$("$B/chrome_exec.sh" "$B/guard.js")
    echo "  progress $n guard $(echo "$g" | python3 -c "import json,sys;g=json.load(sys.stdin);print('captcha',g['captcha'],'login',g['loginRedirect'])" 2>/dev/null)"
    if echo "$g" | grep -q '"captcha":true\|"loginRedirect":true'; then echo "STOP guard: $g"; break; fi
  fi
done
rm -f "$GO"; echo "done"
