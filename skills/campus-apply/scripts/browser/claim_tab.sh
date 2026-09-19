#!/bin/zsh
# 用法：claim_tab.sh <窗口号> <标签号> [运行ID]
# 认领一个标签页：往它的 sessionStorage 写 __caClaim=<运行ID>，之后所有脚本用 TAB_MARK=<运行ID> 找它。
# 输出：运行ID<TAB>URL。窗口号/标签号来自 list_tabs.sh。跨域跳转会丢标记，需重新认领。
W="$1"; T="$2"; ID="${3:-ca$(date +%s | tail -c 6)}"
osascript - "$W" "$T" "$ID" <<'APPLESCRIPT' 2>/dev/null
on run argv
  set wi to (item 1 of argv) as integer
  set ti to (item 2 of argv) as integer
  set runId to item 3 of argv -- 不能叫 id，那是 AppleScript 保留属性
  tell application "Google Chrome"
    set t to tab ti of window wi
    execute t javascript ("sessionStorage.setItem('__caClaim','" & runId & "'); 'ok'")
    return runId & (ASCII character 9) & (URL of t)
  end tell
end run
APPLESCRIPT
