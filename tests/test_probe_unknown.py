"""探测报不出值时必须说"读不出"，不能说"是空的"。

容器型控件（日期选择器、下拉）的值挂在内层 input 上，容器本身是个 span。按容器读
`innerText` 永远是空字符串，于是整类字段被报成 `valueLen: 0`——下游看到"空"就可能去补填，
把用户已经填好的内容覆盖掉。这是整个仓库里唯一能动到真实数据的缺陷类型，所以单独一组测试。

这里只验源码契约。真页面上的取值行为归 `evals/container_value_check.py`（要浏览器，
不进这组无依赖测试）。
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
BROWSER = HERE.parent / 'skills/campus-apply/scripts/browser'
PROBE = BROWSER / 'probe.js'
PRINCIPLES = HERE.parent / 'skills/apply-fill/references/on-site-principles.md'


def code_of(path):
    """去掉行注释，只留可执行部分 —— 注释里提到某个词不算实现了它。"""
    text = path.read_text(encoding='utf-8')
    return '\n'.join(l for l in text.splitlines() if not l.strip().startswith('//'))


def test_probe_separates_unknown_from_empty():
    """读不出和确实是空必须是两个不同的信号，不能共用 valueLen == 0。"""
    code = code_of(PROBE)
    assert 'valueUnknown' in code, 'probe 要能报"读不出"，不能一律报空'


def test_probe_says_which_layer_the_value_came_from():
    """值是从控件本身、内层 input 还是显示元素读到的，可信度不同，要报出来。"""
    assert 'valueFrom' in code_of(PROBE), '要说明值读自哪一层，便于判断可信度'


def test_probe_drills_into_the_inner_input_of_a_container():
    """容器型控件（外层是 span/div，值在内层 input 上）要往下钻一层取值。"""
    code = code_of(PROBE)
    assert 'innerValueEl' in code, '要显式找容器内的输入控件，而不是直接读容器的 innerText'


def test_empty_is_only_claimed_when_an_input_was_actually_found():
    """只有真的找到了输入控件、它的值是空串，才允许说"空"。"""
    code = code_of(PROBE)
    assert 'valueUnknown' in code and 'valueFrom' in code
    # 容器没有任何输入控件、也没有显示值元素时，不能落到"读了 innerText，是空的"这条路上
    assert 'box.innerText' not in code, \
        '按容器 innerText 取值就是 #118 的病根：容器没有文本不等于字段是空的'


def test_the_rule_is_written_down_for_the_model_too():
    """代码改了，规矩也要写进 skill —— 不然模型仍然会把"探测报空"当成"没填"。"""
    text = PRINCIPLES.read_text(encoding='utf-8')
    assert '探测报空' in text or 'valueUnknown' in text, \
        'on-site-principles 要写明"探测报空不等于没填"，容器型控件先下钻确认'
