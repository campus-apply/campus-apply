# 第一次在这台机器上用

同一台机器只需要走一次，除非后面报错像是缺依赖。

## 探 Python

依次试 `py -3 --version`、`python3 --version`、`python --version`，用第一个能打出版本号的
（Windows 上 `python` 可能是应用商店的占位程序，没有输出、退出码 49，不算有）。

没有或低于 3.9，把安装命令给用户，等用户装完再继续：

- Windows：`winget install Python.Python.3.12`
- macOS：`brew install python`
- 其他：python.org

后面所有 `python3 …` 命令都换成探到的那个。

## 跑 doctor

有 Python 就跑 `python3 <本skill>/scripts/doctor.py`，每行是"状态、项目、说明、修复命令"。

- 缺 pip 包：问一句"缺 X、Y，我现在装？"，用户同意就 `doctor.py --install`（只装缺的），
  装完把结果给用户看。
- 缺浏览器、Git：把那一行的命令原样给用户，等用户装完说一声再重跑 doctor。
- Word、pdftoppm 是可选项，没有就照常走。

全部必需项 OK 之后才进 resume-facts。
