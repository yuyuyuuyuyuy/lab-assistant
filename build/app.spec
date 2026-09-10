# -*- mode: python ; coding: utf-8 -*-
# 「药鉴」PyInstaller 打包配置：onedir（文件夹模式，误报率低于 onefile）
import os

from PyInstaller.utils.hooks import collect_all

# 应用根目录（SPECPATH 是 spec 文件所在目录=app/build，再上一级即 app 根目录）
APP_ROOT = os.path.dirname(os.path.abspath(SPECPATH))

datas, binaries, hiddenimports = [], [], []
# 有原生扩展/资源文件的包：整包收集（sqlite-vec 带 vec0.dll、webview 带 js 资源等）
for pkg in ("sqlite_vec", "webview", "pythonnet", "clr_loader", "pymupdf", "charset_normalizer", "PIL", "pptx"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# 应用自带资源：前端、提示词、图标、内置语料、本地 Key 文件
datas += [
    (os.path.join(APP_ROOT, "frontend"), "frontend"),
    (os.path.join(APP_ROOT, "prompts"), "prompts"),
    (os.path.join(APP_ROOT, "res"), "res"),
    (os.path.join(APP_ROOT, "local_key.txt"), "."),
]

a = Analysis(
    [os.path.join(APP_ROOT, "main.py")],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="YaoJian",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # 不用 UPX：降低杀软误报概率
    console=False,      # 无控制台窗口
    icon=os.path.join(APP_ROOT, "res", "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="YaoJian",
)
