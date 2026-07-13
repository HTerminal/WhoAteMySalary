# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Mail Money Tracker.

Builds a one-folder, WINDOWED (no console) desktop app named "MailMoneyTracker",
entry point app.py.

Build locally with:
    pyinstaller MailMoneyTracker.spec

This file is intentionally git-tracked (see the "!MailMoneyTracker.spec" exception
in .gitignore) so the release CI can use it verbatim on every OS.

Notes:
- config.example.json is bundled next to the executable as the shipped template.
  Real user data (config.json, tokens.json, data.db, cache.db) is created at
  runtime in the user's own directory and is never bundled.
- No custom icon is set here on purpose: the app draws its own window/tray icon
  at runtime, so we don't need an .ico/.icns asset to build a release.
- Hidden imports and collected packages are platform-specific. The Windows
  notification stack (windows-toasts -> winotify) and the pywin32 modules used by
  notify.py to create the Start-Menu shortcut / AppUserModelID are only pulled in
  on Windows. On macOS/Linux the notification fallback is plyer, which PyInstaller
  discovers automatically, so nothing extra is needed there.
"""

import sys

from PyInstaller.utils.hooks import collect_all

# --- Data files bundled into the app ----------------------------------------
# (source_path, destination_dir_inside_bundle)
datas = [
    ("config.example.json", "."),
]

binaries = []
hiddenimports = []

# --- Platform-specific dependencies -----------------------------------------
if sys.platform == "win32":
    # Windows toast backends. collect_all pulls in submodules, data files and
    # any dynamic libraries (winsdk ships compiled WinRT projection modules that
    # PyInstaller's static analysis would otherwise miss).
    for pkg in ("windows_toasts", "winsdk", "winotify"):
        try:
            pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
            datas += pkg_datas
            binaries += pkg_binaries
            hiddenimports += pkg_hiddenimports
        except Exception:
            # A missing optional package must not abort the build; the app
            # degrades gracefully at runtime (winotify -> plyer -> console).
            pass

    # pywin32 pieces used by notify.py for the Start-Menu shortcut + AUMID.
    # notify.py imports pythoncom, win32com.client (Dispatch) and
    # win32com.propsys (propsys, pscon); win32timezone is imported lazily by
    # pywin32 and is a classic missing hidden import.
    hiddenimports += [
        "pythoncom",
        "win32com",
        "win32com.client",
        "win32com.propsys",
        "win32timezone",
    ]
# else: macOS / Linux -> plyer is a plain pip package that PyInstaller finds
# on its own; no extra hidden imports or collection required.

block_cipher = None


a = Analysis(
    ["app.py"],
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
    [],
    exclude_binaries=True,
    name="MailMoneyTracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # windowed app (no console window)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # app draws its own icon at runtime
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MailMoneyTracker",
)

# On macOS, wrap the one-folder build into a proper .app bundle so it launches
# from Finder and shows up with the right name.
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="MailMoneyTracker.app",
        icon=None,
        bundle_identifier="com.mailmoneytracker.desktop",
        info_plist={
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.finance",
        },
    )
