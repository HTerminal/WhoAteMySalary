# -*- coding: utf-8 -*-
"""Windows desktop notifications that land in the Action Center with sound and
show the app's real name.

Primary backend: `windows-toasts` (WinRT — talks to Windows.UI.Notifications
directly, no powershell.exe, so the toast is correctly attributed to this app,
persists in the notification panel, and plays the default sound).
Fallbacks: winotify -> plyer -> console.

Registers an AppUserModelID (AUMID) under HKCU (per-user, no admin, no shortcut)
so Windows shows the app name/icon and keeps the toast in the panel."""
APP_ID = "MailMoneyTracker.Desktop"     # must match the registered AUMID exactly
APP_NAME = "Mail Money Tracker"


def _register_aumid():
    """Register the AUMID under HKCU so toasts are attributed to us and persist."""
    try:
        import winreg
        path = r"Software\Classes\AppUserModelId\%s" % APP_ID
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as k:
            winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(k, "ShowInSettings", 0, winreg.REG_DWORD, 1)
    except Exception:
        pass


def _ensure_shortcut():
    """Windows only shows toasts from an unpackaged app if a Start-Menu shortcut
    carrying the AUMID exists. Create one (per-user, no admin) on first run."""
    try:
        import os
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return
        here = os.path.dirname(os.path.abspath(__file__))
        script = next((os.path.join(here, c) for c in ("app.py", "gui.py")
                       if os.path.isfile(os.path.join(here, c))), None)
        if not script:
            return
        lnk = os.path.join(appdata, "Microsoft", "Windows", "Start Menu",
                           "Programs", APP_NAME + ".lnk")
        if os.path.exists(lnk):
            return                      # already set up (idempotent)
        import sys
        import pythoncom
        from win32com.client import Dispatch
        from win32com.propsys import propsys, pscon
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.isfile(pyw):
            pyw = sys.executable
        shell = Dispatch("WScript.Shell")
        sc = shell.CreateShortcut(lnk)
        sc.TargetPath = pyw
        sc.Arguments = '"%s"' % script
        sc.WorkingDirectory = here
        sc.IconLocation = "%s,0" % pyw
        sc.save()
        store = propsys.SHGetPropertyStoreFromParsingName(
            lnk, None, 0x2, propsys.IID_IPropertyStore)   # GPS_READWRITE
        store.SetValue(pscon.PKEY_AppUserModel_ID,
                       propsys.PROPVARIANTType(APP_ID, pythoncom.VT_LPWSTR))
        store.Commit()
    except Exception as e:
        print("[notify] Start-Menu shortcut setup skipped:", e)


_register_aumid()
_ensure_shortcut()

_backend = None
_toaster = None
_WT = None

# 1) windows-toasts (WinRT) — most reliable: correct attribution + Action-Center
#    persistence + default sound, no powershell subprocess.
try:
    from windows_toasts import InteractableWindowsToaster, Toast, ToastAudio, AudioSource
    _toaster = InteractableWindowsToaster(APP_NAME, notifierAUMID=APP_ID)
    _WT = (Toast, ToastAudio, AudioSource)
    _backend = "windows-toasts"
except Exception:
    # 2) winotify (PowerShell toast)
    try:
        from winotify import Notification, audio
        _backend = "winotify"
    except Exception:
        # 3) plyer
        try:
            from plyer import notification as _plyer
            _backend = "plyer"
        except Exception:
            _backend = None


def notify(title, message, url=None, on_click=None):
    """Show a desktop notification (with sound). Returns True if shown via a real
    Windows toast backend. on_click() is called when the user clicks the toast
    (windows-toasts backend)."""
    try:
        if _backend == "windows-toasts":
            Toast, ToastAudio, AudioSource = _WT
            toast = Toast(text_fields=[str(title), str(message)])
            try:
                toast.audio = ToastAudio(AudioSource.Default, silent=False)
            except Exception:
                pass
            if on_click:
                try:
                    toast.on_activated = lambda *_: on_click()
                except Exception:
                    pass
            _toaster.show_toast(toast)
            return True
        elif _backend == "winotify":
            n = Notification(app_id=APP_ID, title=title, msg=message)
            try:
                n.set_audio(audio.Default, loop=False)
            except Exception:
                pass
            if url:
                n.add_actions(label="Open", launch=url)
            n.show()
            return True
        elif _backend == "plyer":
            _plyer.notify(title=title, message=message, app_name=APP_NAME, timeout=10)
            return True
        else:
            print(f"[NOTIFY] {title} - {message}  {url or ''}")
            return False
    except Exception as e:
        print(f"[NOTIFY-ERROR] {e} :: {title} - {message}")
        return False


def test():
    """Fire a sample notification so users can verify alerts without a real event."""
    return notify(f"{APP_NAME}: test notification",
                  "If this appears in your notification panel with a sound, alerts work.")


def backend():
    return _backend or "console"
