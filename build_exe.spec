# PyInstaller — cửa sổ desktop (pywebview) + Flask nội bộ
# Chạy: pyinstaller build_exe.spec --noconfirm

from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

datas = [
    ("templates", "templates"),
    ("static", "static"),
]
datas += collect_data_files("certifi")

binaries = []
hiddenimports = [
    "license_guard",
    "filter",
    "app",
    "webapp",
    "runtime_paths",
]

for pkg in ("webview",):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        hiddenimports.append(pkg)

a = Analysis(
    ["desktop_app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="AffiliateOfferFilter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
