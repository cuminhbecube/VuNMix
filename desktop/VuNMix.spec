# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all


# esptool ships ESP32-family flasher stubs as package data (JSON/binary files).
# PyInstaller does not include these automatically when only hidden imports are
# listed, so collect the complete package to keep firmware updates functional
# in the windowed VuNMix build.
esptool_datas, esptool_binaries, esptool_hiddenimports = collect_all("esptool")


a = Analysis(
    ["vunmix.py"],
    pathex=[],
    binaries=esptool_binaries,
    datas=[("assets", "assets")] + esptool_datas,
    hiddenimports=[
        "win32api",
        "win32con",
        "win32gui",
        "win32ui",
    ] + esptool_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VuNMix",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["assets\\icon.ico"],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VuNMix",
)
