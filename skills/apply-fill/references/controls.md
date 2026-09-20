# 控件处理办法

参考实现：`../campus-apply/scripts/browser/lib_antd3.js`（`window.__ca`，antd 3.x）。下面按 UI 框架分，选择器以现场为准。

## 文本写入的标准序列
- 原型上的 value setter 赋值 → 派发 `input` → 派发 `change` → 派发 `FocusEvent('blur')` 和 `focusout`。受控组件常常只在失焦时才把值交给表单模型，不派发失焦事件的话显示值、字数统计全对，保存后却是空的。后台标签页里 `el.focus()` / `el.blur()` 不会触发焦点事件，所以事件要自己派发。
- 写完读三层核对：显示值、DOM `value`、框架模型值（React 从元素的 `__reactFiber$…` 属性沿 `return` 往上找带 `memoizedProps.value` 的节点；Vue 看 `__vue__` 或 `__vueParentComponent`）。三层一致才算写进去。

## 两种点法
- 页面脚本里的 `el.click()` 是合成事件，多数控件认，但有的控件只认真实鼠标事件。脚本点了没反应、面板不出现，就换 `chrome_cdp.py --mark <ID> click <目标>`：它通过浏览器发真实鼠标事件，目标可以是 CSS 选择器、`js:` 表达式（求值得到元素，适合按文本找菜单项）或视口坐标。
- 探控件类型时，"合成点击没反应、真实点击有反应"也是一条结论，记进站点笔记，同一站后面直接用 `click`。
- 有的站点把没提交的表单内容存在浏览器本地存储（`localStorage`）里，刷新也不消失；要撤销试探性写入，先看有没有这样的键，删掉再刷新。哪个站怎么存，探到了记站点笔记。

## antd 3.x

- 文本框/文本域：用原型上的 value setter 赋值，再派发 `input` 和 `change` 事件，React 才能感知。
- 日期（只读的 `ant-calendar-picker-input`）：点输入框打开面板 → 往面板里的 `input.ant-calendar-input` 写 `YYYY-MM-DD` → 再点一次输入框收起 → 轮询等面板消失。面板挂在 body 下，按位置匹配（面板顶边≈输入框底边，或面板底边≈输入框顶边）。清空用 `.ant-calendar-picker-clear`。
- 下拉（`ant-select`）：点 `.ant-select-selection` 打开，下拉列表也挂在 body 下，同样按位置匹配（上下弹出都要认），再点 `li.ant-select-dropdown-menu-item`。多选下拉点多次即可。
- 搜索型下拉（学校名称）：打开后往 `input.ant-select-search__field` 写关键词，等接口返回再点选项。
- 级联（`ant-cascader`）：点输入框打开 `.ant-cascader-menus`，逐级点 `li`；选中值显示在 `.ant-cascader-picker-label`，不在 input 里。
- 单选：点对应 `label.ant-radio-wrapper`。
- 删除：点删除按钮会弹 antd-mobile 确认框，点其中的"确认"。


## 其他 UI 框架
- antd 4/5：日期是 `.ant-picker`，下拉是 `.ant-select` + `.ant-select-dropdown`（结构与 3.x 不同，选项是 `.ant-select-item-option`）；面板同样挂 body 下，按位置匹配的思路不变，选择器要现场看。
- Element UI（Vue）：`.el-input__inner`、`.el-select` + `.el-select-dropdown`、`.el-date-editor`；赋值同样要用原型 setter + input 事件。
- 原生 `<select>`：直接改 `value` 再派发 `change`。
- 现场探测：先跑 `probe.js` 看 `kind` 和 `cls`，再决定用哪套写法；写成功后记进站点笔记。
- class 带发版哈希后缀（如 Moka 的 `search-LvPmRxVfY4`）：用前缀匹配 `[class^="search-"]` 或 `[class*="search-"]`，不要写死整个 class。

## Moka（`sd-` 前缀组件）
- 字段容器 `[class*="apply-field-"]`，文本以字段标题开头；板块容器 `[class*="apply-block-"]`，条目组 `[class*="apply-fields-"]`，每个板块的"添加"按钮加一组。
- 纯下拉与级联：点输入框打开，选项是 `[class*="sd-Menu-content-item"]`（挂 body 下）；级联点第一级后第二级项出现在同一选择器里；点选项即选中，选中值显示在 `span[class*="sd-Input-display-value"]`，`input.value` 恒为空，回读要读显示值。关面板点该字段的标题。
- 可搜索下拉（年、月、学校名称）：点输入框 → 用原生 setter 输入 → 在这个输入框自己的菜单里（按位置匹配）点完全相等的项 → 核对显示值。只输入不点菜单项，值不会选中，菜单也不会关。月份的选项是 1 到 12，不带前导零。
- 文本框、文本域：原生 setter + input/change 事件有效。"至今"是 `sd-Checkbox-input-*`。
- 日期面板（出生日期）：只读输入框，合成点击打不开，用 `click` 发真实鼠标事件才打开；年份用双箭头翻、再点月、再点日；翻页太多时交给用户手点更快。
- 错误提示 `div[class*="sd-Input-error"]` 可能滞后，不作填没填的判据。
- 探选项时同一元素可能被多个选择器命中而重复，去重后再列给用户。
