#!/bin/zsh
# 用法：list_tabs.sh [过滤关键字]
# 列出 Chrome 所有窗口的标签页：窗口号<TAB>标签号<TAB>标题<TAB>URL。给了关键字只列 URL 或标题含它的。
# 用途：认领工作标签页前给用户看，避免误操作用户自己打开的页面。
KW="${1:-}"
osascript - "$KW" <<'APPLESCRIPT' 2>/dev/null
on run argv
  set kw to item 1 of argv
  set out to ""
  set d to (ASCII character 9) -- 在 tell Chrome 块里 tab 会被当成 Chrome 的 tab 类，所以先取制表符
  tell application "Google Chrome"
    set wi to 0
    repeat with w in windows
      set wi to wi + 1
      set ti to 0
      repeat with t in tabs of w
        set ti to ti + 1
        set u to URL of t
        set tt to title of t
        if kw is "" or u contains kw or tt contains kw then
          set out to out & wi & d & ti & d & tt & d & u & linefeed
        end if
      end repeat
    end repeat
  end tell
  return out
end run
APPLESCRIPT
