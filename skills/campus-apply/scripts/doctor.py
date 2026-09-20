#!/usr/bin/env python3
"""检查这台机器上 campus-apply 需要的东西，缺什么给出这台机器上该敲的命令。只用标准库。

用法：
  doctor.py            逐项检查，每行：状态<TAB>项目<TAB>说明<TAB>修复命令；必需项有缺退出码 1
  doctor.py --install  先检查，再用当前 Python 安装缺的 pip 包（只装缺的），装完换一个新进程重新检查
                       （刚装的包在原进程里探测不到：导入缓存和启动时不存在的 site 目录）

状态：OK 齐全；缺 必需项缺失；可选 可选项缺失（流程能走，某一步降级）。
系统级的东西（Python、浏览器、Git、Word）脚本不代装，只给命令或链接。
"""
import importlib.util, json, os, shutil, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'browser'))

PACKAGES = [('python-docx', 'docx', '改简历：读写 docx'), ('openpyxl', 'openpyxl', '筛岗：生成 Excel'),
            ('pypdf', 'pypdf', '读 PDF 正文（事实库材料）与核 PDF 页数'), ('docx2pdf', 'docx2pdf', '改简历：Windows 上用 Word 导 PDF')]

WORD_PATHS = {
    'darwin': ['/Applications/Microsoft Word.app'],
    'win32': [os.path.join(os.environ.get('PROGRAMFILES', r'C:\Program Files'), 'Microsoft Office', 'root', 'Office16', 'WINWORD.EXE'),
              os.path.join(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)'), 'Microsoft Office', 'root', 'Office16', 'WINWORD.EXE')],
}


VERSION_FILE = os.path.join(HERE, '..', 'VERSION')
RELEASES_API = 'https://api.github.com/repos/campus-apply/campus-apply/releases/latest'


def local_version():
    try:
        return open(VERSION_FILE, encoding='utf-8').read().strip()
    except OSError:
        return '?'


def latest_version(timeout=3):
    """GitHub 上最新 release 的版本号；没网、超时、被拦、接口变了都返回 None，从不抛错。"""
    try:
        with urllib.request.urlopen(urllib.request.Request(RELEASES_API, headers={'Accept': 'application/vnd.github+json'}), timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8')).get('tag_name', '').lstrip('v') or None
    except Exception:
        return None


def newer(a, b):
    """a 比 b 新？两边都是 x.y.z。"""
    try:
        return tuple(int(x) for x in a.split('.')) > tuple(int(x) for x in b.split('.'))
    except ValueError:
        return False


class Machine:
    """检查所依赖的环境事实，可整体替换以便测试。"""

    def __init__(self, platform=None, version=None, modules=None, which=None, browser='auto', paths=None, python=None,
                 free_gb='auto', latest='auto'):
        self.platform = platform or sys.platform
        self.version = version or tuple(sys.version_info[:3])
        self.python = python or sys.executable
        self._modules, self._which, self._browser, self._paths = modules, which, browser, paths
        self._free_gb, self._latest = free_gb, latest

    def free_gb(self):
        if self._free_gb != 'auto':
            return self._free_gb
        try:
            return shutil.disk_usage(os.getcwd()).free / 1e9
        except OSError:
            return None

    def latest(self):
        return latest_version() if self._latest == 'auto' else self._latest

    def has_module(self, name):
        if self._modules is not None:
            return name in self._modules
        return importlib.util.find_spec(name) is not None

    def has_cmd(self, name):
        if self._which is not None:
            return name in self._which
        return shutil.which(name) is not None

    def browser_path(self):
        if self._browser != 'auto':
            return self._browser
        from chrome_cdp import find_browser
        return find_browser()

    def exists(self, path):
        if self._paths is not None:
            return path in self._paths
        return os.path.exists(path)

    @property
    def win(self):
        return self.platform.startswith('win')


class Result:
    def __init__(self, name, ok, detail, fix='', required=True):
        self.name, self.ok, self.detail, self.fix, self.required = name, ok, detail, fix, required

    def line(self):
        status = 'OK' if self.ok else ('缺' if self.required else '可选')
        return f'{status}\t{self.name}\t{self.detail}\t{self.fix}'


def run_checks(m):
    rs = []
    v = '.'.join(map(str, m.version))
    fix = 'winget install Python.Python.3.12（或 https://www.python.org/downloads/ ）' if m.win else 'brew install python（或 https://www.python.org/downloads/ ）'
    rs.append(Result('python', m.version >= (3, 9), f'Python {v}，需要 3.9 以上', '' if m.version >= (3, 9) else fix))
    for pip_name, mod, why in PACKAGES:
        if pip_name == 'docx2pdf' and not m.win:
            continue  # macOS 用 Word 自己导 PDF，不需要它
        ok = m.has_module(mod)
        if pip_name == 'pypdf' and not ok and m.has_cmd('pdftotext'):
            rs.append(Result('pypdf', True, '没装 pypdf，但有 pdftotext 可以读 PDF 正文和核页数'))
            continue
        required = pip_name != 'docx2pdf'
        rs.append(Result(pip_name, ok, why, '' if ok else f'{m.python} -m pip install {pip_name}', required))
    b = m.browser_path()
    fix = 'winget install Google.Chrome（Windows 自带的 Edge 也可以）' if m.win else 'brew install --cask google-chrome（或 https://www.google.com/chrome/ ）'
    rs.append(Result('browser', bool(b), b or '没找到 Chrome / Edge；装在别处可设 CA_BROWSER=<可执行文件路径>', '' if b else fix))
    fix = 'winget install Git.Git' if m.win else 'xcode-select --install 或 brew install git'
    rs.append(Result('git', m.has_cmd('git'), '只在从 GitHub 安装或更新插件时用到；没有它可以下载 zip 解压后按本地目录安装', '' if m.has_cmd('git') else fix, required=False))
    fix = 'winget install oschwartz10612.Poppler 后把其 bin 目录加进 PATH（或 https://github.com/oschwartz10612/poppler-windows/releases ）' if m.win else 'brew install poppler'
    rs.append(Result('pdftoppm', m.has_cmd('pdftoppm'), '看图片型 PDF（扫描件、网申导出）和核对简历版面时把页面转成图；没有就用 pypdf 抽图或请用户截图',
                     '' if m.has_cmd('pdftoppm') else f'{fix}；或 {m.python} -m pip install pymupdf（纯 pip，效果相同）', required=False))
    word = any(m.exists(p) for p in WORD_PATHS.get('win32' if m.win else 'darwin', []))
    rs.append(Result('word', word, '改简历时用 Word 导 PDF 核页数', '' if word else '没有 Word 就跳过核页数，改简历时会明确说"未核页数"', required=False))
    free = m.free_gb()
    if free is not None:
        low = free < 1
        rs.append(Result('disk', not low, f'当前盘剩余 {free:.1f} GB；截图、PDF、浏览器缓存都要占空间',
                         '剩余不足 1 GB，先清出空间再开始（专用浏览器配置目录可以整个删）' if low else '', required=False))
    local, latest = local_version(), m.latest()
    if latest and newer(latest, local):
        rs.append(Result('version', True, f'campus-apply {local}，有新版 {latest}',
                         '更新：/plugin marketplace update campus-apply → /plugin update campus-apply@campus-apply → 你自己输 /reload-plugins；'
                         'Codex 是 codex plugin marketplace upgrade campus-apply → codex plugin add campus-apply@campus-apply；'
                         '用 install.sh 装的重新拉仓库再跑一遍 install.sh'))
    else:
        rs.append(Result('version', True, f'campus-apply {local}'))
    return rs


def pip_missing(rs, m):
    """缺的、能直接 pip 装的项：修复命令就是 <python> -m pip install <项目名>。"""
    return [r for r in rs if not r.ok and r.fix == f'{m.python} -m pip install {r.name}']


def pip_command(rs, m=None):
    """把缺的 pip 包合成一条安装命令，没有缺的返回空串。"""
    m = m or Machine()
    missing = pip_missing(rs, m)
    return f'{m.python} -m pip install ' + ' '.join(r.name for r in missing) if missing else ''


def install_missing(rs, m):
    """只装缺的 pip 包，逐个装，返回失败的包名列表。"""
    failed = []
    for r in pip_missing(rs, m):
        if subprocess.run([m.python, '-m', 'pip', 'install', r.name]).returncode != 0:
            failed.append(r.name)
    return failed


def exit_code(rs):
    return 1 if any(r.required and not r.ok for r in rs) else 0


def recheck_in_fresh_process(python):
    """装完后在新进程里重新检查并输出，返回它的退出码。"""
    return subprocess.run([python, os.path.abspath(__file__)]).returncode


def main(argv):
    if any(a in ('-h', '--help') for a in argv):
        print(__doc__)
        return 0
    m = Machine()
    rs = run_checks(m)
    if '--install' in argv:
        failed = install_missing(rs, m)
        if failed:
            print('# 安装失败：' + ' '.join(failed))
        return recheck_in_fresh_process(m.python)
    for r in rs:
        print(r.line())
    cmd = pip_command(rs, m)
    if cmd:
        print(f'# 一次装齐缺的包：{cmd}')
    return exit_code(rs)


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
    sys.exit(main(sys.argv[1:]))
