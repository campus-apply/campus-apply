#!/bin/zsh
# 用法：TAB_MARK=<运行ID> chrome_exec.sh <js文件>      按认领标记找标签页（推荐，见 claim_tab.sh）
#       TAB_MATCH=<url片段> chrome_exec.sh <js文件>   按 URL 子串找第一个匹配的标签页（兜底）
# 在找到的标签页里执行 JS 文件，输出最后一个表达式的值。
# 前提：Chrome 菜单栏 显示 → 开发者 → 勾选"允许 Apple 事件中的 JavaScript"。
# 输出 NO_MATCHING_TAB 表示没找到；以 ERR_APPLE_EVENTS 开头表示未开权限。
JS="$1"
[ -f "$JS" ] || { echo "ERR_NO_FILE $JS"; exit 2; }
JS="$(cd "$(dirname "$JS")" && pwd)/$(basename "$JS")"   # 相对路径会让 osascript 报 CFURLGetFSRef 警告
MARK="${TAB_MARK:-}"; MATCH="${TAB_MATCH:-}"
[ -n "$MARK$MATCH" ] || { echo "ERR_NEED_TAB_MARK_OR_TAB_MATCH"; exit 2; }
osascript - "$JS" "$MARK" "$MATCH" <<'APPLESCRIPT' 2>&1 | sed -e 's/^.*Executing JavaScript through AppleScript is turned off.*$/ERR_APPLE_EVENTS: 请在 Chrome 菜单 显示→开发者 勾选"允许 Apple 事件中的 JavaScript"/'
on run argv
  set jsPath to item 1 of argv
  set mark to item 2 of argv
  set matchStr to item 3 of argv
  set js to read POSIX file jsPath as «class utf8»
  set probe to "(function(){try{return sessionStorage.getItem('__caClaim')||''}catch(e){return ''}})()"
  tell application "Google Chrome"
    repeat with w in windows
      repeat with t in tabs of w
        set u to URL of t
        if u starts with "http" then
          if mark is not "" then
            try
              if (execute t javascript probe) is mark then return execute t javascript js
            end try
          else if u contains matchStr then
            return execute t javascript js
          end if
        end if
      end repeat
    end repeat
    return "NO_MATCHING_TAB"
  end tell
end run
APPLESCRIPT
