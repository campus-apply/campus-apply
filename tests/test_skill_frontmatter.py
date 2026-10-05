import os, re
HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.join(HERE, '..', 'skills')


def frontmatter(name):
    text = open(os.path.join(SKILLS, name, 'SKILL.md'), encoding='utf-8').read()
    body = text.split('---\n', 2)[1]
    return dict(line.split(': ', 1) for line in body.splitlines())


def plain_scalar_is_strict_yaml(value):
    """严格 YAML 解析器眼里合法的裸值：里面不能再出现"冒号+空格"，也不能有" #"。"""
    return ': ' not in value and ' #' not in value


def test_description_survives_a_strict_yaml_parser():
    for name in sorted(os.listdir(SKILLS)):
        fm = frontmatter(name)
        value = fm['description']
        if value[0] in '"\'':
            assert value[-1] == value[0] and value[0] not in value[1:-1], name
        else:
            assert plain_scalar_is_strict_yaml(value), f'{name}: description 里有"冒号+空格"，严格 YAML 会当成嵌套映射，要加引号'


def test_name_matches_directory():
    for name in sorted(os.listdir(SKILLS)):
        assert frontmatter(name)['name'] == name


def test_description_says_when_to_use_not_what_it_does():
    """description 的作用是让模型判断"现在要不要加载这份 skill"，所以只写触发条件。

    把工作流摘要写进 description 会造成一条捷径：模型照着那句话做，正文就被跳过了。
    这套 skill 的每一份正文都是多步流程，被跳过的代价是整步整步地漏。
    """
    for name in sorted(os.listdir(SKILLS)):
        value = frontmatter(name)['description'].strip('"\'')
        assert value.startswith('Use when'), \
            f'{name}: description 要以 "Use when" 开头，只说什么时候用它'
        head = value.split('triggers:')[0]
        for word in ('步骤', '第一步', '先…再', '然后', '流程是', '依次'):
            assert word not in head, f'{name}: description 里不要概括工作流（出现了「{word}」）'


def test_description_keeps_chinese_triggers_for_search():
    """触发词要带中文：用户说的是中文，而 description 是拿去跟用户的话做匹配的。"""
    for name in sorted(os.listdir(SKILLS)):
        value = frontmatter(name)['description']
        assert any('\u4e00' <= ch <= '\u9fff' for ch in value), \
            f'{name}: description 里要有中文触发词，用户不会用英文说"帮我填表"'
