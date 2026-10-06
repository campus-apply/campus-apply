# 控件操作：现场证据与已声明目标

## 先判断当前控件
用survey、DOM与必要的截图确定它是字段/动作/面板/显示节点。框架名与class不是行为保证；不按Moka、antd或其他系统名称选择固定点法。下列方法是可选工具，由agent根据本页证据采用。

## 文本与原生控件
文本默认fill：原型value setter、input/change、blur/focusout，写后回读。目标已明确但setter无效时可用type的真实浏览器输入路径；两次无效交接。
原生select读取native_options（显示文字、编码value、节点和索引）。重名不取第一项，agent明确给option_selector；回读核对实际value与selectedIndex。文字与编码不同不是写入失败的理由。
checkbox/radio只按用户已定的数据/意愿改变，不为探测去勾；有后果的选项按collect-table处理。

## 自定义控件与真实鼠标
click支持CSS、返回元素的js表达式或DOM精确计算的坐标。执行前检查连接、可见和遮挡；面板、选项各有明确目标。多候选用panel_selector/option_selector；多级用按步骤的数组，每步重新验证，不要求第二级一定开新面板。
搜词和选择是两件动作，输入词不等于选中。显示值可能在别处，由agent确认display_selector，不按类名或最长文字猜。
关闭动作在本页核验，旧节点移除但新候选出现要看图判断，不能谎报已关闭。禁止document.body.click()和合成键盘事件；可用现有click发真实鼠标。

## 特殊情况与参考代码
fill表达不了的控件，agent可在已授权范围内用click/type/exec/stage现场操作并回读；不因统一工具无能力停在无解循环，不为每个正常字段另写脚本。
lib_antd3.js保留为历史实现参考，不是框架识别器或本站保证。选择器只来自本次现场确认；不把一页成功的class/层级/关闭招式写成长期跨站结论。删除、覆盖、清空已有值先说明后果与已确认授权，不预言必有某类确认框。
