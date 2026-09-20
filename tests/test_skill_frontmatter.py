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
