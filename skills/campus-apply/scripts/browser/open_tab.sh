#!/bin/zsh
# 用法：open_tab.sh <URL> [运行ID]
# 在 Chrome 第一个窗口新开一个标签页打开 URL，等待加载后写入认领标记，输出：运行ID<TAB>URL。
# 用途：需要同时保留两个页面状态（如申请表与在线简历）时，由我们自己开第二个标签页，不占用用户的页面。
URL="$1"; ID="${2:-ca$(date +%s | tail -c 6)}"
osascript - "$URL" "$ID" <<'APPLESCRIPT' 2>/dev/null
on run argv
  set theUrl to item 1 of argv
  set runId to item 2 of argv
  tell application "Google Chrome"
    tell window 1
      set t to make new tab with properties {URL:theUrl}
    end tell
    -- 等页面真正加载完再写标记（新标签页头几秒可能还是空白页，写了也没用）
    repeat with k from 1 to 20
      delay 0.5
      try
        if (loading of t) is false then exit repeat
      end try
    end repeat
    delay 1
    execute t javascript ("sessionStorage.setItem('__caClaim','" & runId & "'); 'ok'")
    return runId & (ASCII character 9) & (URL of t)
  end tell
end run
APPLESCRIPT
