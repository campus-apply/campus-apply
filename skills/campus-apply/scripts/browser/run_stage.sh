#!/bin/zsh
# 用法：TAB_MARK=<运行ID>（或 TAB_MATCH=<url片段>） [LIBS="lib1.js lib2.js"] run_stage.sh <stage.js> [最长等待秒数，默认 90]
# 把 LIBS 里的库和 stage 拼成一个脚本注入。stage 写成 (async () => {...})()，用 window.__ca.L() 记日志，结束时 L('DONE')，出错 L('ERR ...')。
# 每次运行发一个 ID，只有本次运行能写全局日志；本脚本轮询到 DONE / ERR / 超时为止。
W=$(dirname "$0"); S="$1"; MAX="${2:-90}"
ID=$(date +%s%N | tail -c 7)
TMP=$(mktemp "${TMPDIR:-/tmp}/ca_stage.XXXXXX.js")
{
  echo "window.__caRun='$ID'; window.__calog='';"
  for f in ${=LIBS}; do cat "$f"; echo ";"; done
  cat "$S"
} > "$TMP"
"$W/chrome_exec.sh" "$TMP" >/dev/null
RD=$(mktemp "${TMPDIR:-/tmp}/ca_read.XXXXXX.js")
echo "(window.__caRun==='$ID' ? (window.__calog||'') : 'STALE:'+(window.__calog||''))" > "$RD"
t=0
while [ $t -lt $MAX ]; do
  sleep 2; t=$((t+2))
  OUT=$("$W/chrome_exec.sh" "$RD")
  if echo "$OUT" | grep -q "DONE\|^ERR\|ERR "; then break; fi
done
echo "$OUT"
[ $t -ge $MAX ] && echo "(timeout ${MAX}s, last log above)"
rm -f "$TMP" "$RD"
