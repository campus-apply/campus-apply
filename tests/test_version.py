import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')


def test_version_file_matches_plugin_and_marketplace_manifests():
    v = open(os.path.join(ROOT, 'skills', 'campus-apply', 'VERSION'), encoding='utf-8').read().strip()
    plugin = json.load(open(os.path.join(ROOT, '.claude-plugin', 'plugin.json'), encoding='utf-8'))['version']
    market = json.load(open(os.path.join(ROOT, '.claude-plugin', 'marketplace.json'), encoding='utf-8'))['plugins'][0]['version']
    assert v == plugin == market
