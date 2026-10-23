"""Capture the actual VuNMix Tk UI with deterministic, disconnected services.

Dependencies: the desktop CustomTkinter, Pillow and pyserial packages, plus a
working native Tk display (Windows desktop or Xvfb on Linux). Run from the repo:

    python desktop/tools/capture_control_center.py --output ./ui-captures

Use --connected for representative connected-state fixture data and
--all-clock-styles to capture each of the sixteen selected styles. --version
can supply a release version when running an unpackaged source checkout.

This QA harness never starts a controller, updater, tray icon, or hardware service.
The native UI widgets and view methods are the production implementations.
Screenshots show the host's native font rendering and window client area; an X11
capture does not validate Windows chrome, DPI, or physical device behavior.
"""
from __future__ import annotations

import argparse
import atexit
import ctypes
import ctypes.util
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import tkinter
import traceback
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sizes", default="1040x680,960x640,780x560")
    parser.add_argument("--connected", action="store_true")
    parser.add_argument("--all-clock-styles", action="store_true")
    parser.add_argument("--clock-style", type=int, choices=range(16), default=0,
                        help="Initially selected protocol clock style (0..15)")
    parser.add_argument("--version")
    parser.add_argument("--scaling", type=float, default=1.0,
                        help="Explicit Tk widget/window scaling, for example 1.5")
    parser.add_argument("--sidebar", choices=("auto", "expanded", "collapsed"),
                        default="auto", help="Exercise manual navigation width overrides")
    parser.add_argument("--assert-layout", action="store_true",
                        help="Fail if managed controls are clipped or hidden")
    return parser.parse_args()


def load_ctk():
    # CTk 5.2 copies its Linux shape/Roboto fonts into ~/.fonts at import time.
    # Redirect only that dependency path, not HOME or any app config location.
    if not sys.platform.startswith("linux"):
        import customtkinter as ctk
        return ctk
    font_dir = Path(tempfile.mkdtemp(prefix="vunmix-qa-fonts-"))
    atexit.register(shutil.rmtree, font_dir, ignore_errors=True)
    original_expanduser = os.path.expanduser

    def font_expanduser(path):
        return str(font_dir) if path == "~/.fonts/" else original_expanduser(path)

    with patch("os.path.expanduser", side_effect=font_expanduser):
        import customtkinter as ctk

    if sys.platform.startswith("linux"):
        fontconfig = ctypes.CDLL(ctypes.util.find_library("fontconfig"))
        fontconfig.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        fontconfig.FcConfigAppFontAddFile.restype = ctypes.c_int
        for font in font_dir.iterdir():
            if font.suffix in (".ttf", ".otf"):
                if not fontconfig.FcConfigAppFontAddFile(None, os.fsencode(font)):
                    raise RuntimeError(f"Could not register QA font {font.name}")
    return ctk


def make_controller(connected):
    from build_info import APP_VERSION
    from protocol import DisplayMode
    from update_coordinator import UpdateCoordinator

    calls = []

    def record(name):
        def callback(*args, **kwargs):
            calls.append((name, repr(args), repr(kwargs)))
            return True
        return callback

    def item(name, volume, default=False, muted=False):
        return SimpleNamespace(name=name, volume=volume, is_default=default,
                               is_muted=muted, _device_id=name,
                               _session_identifier=name)

    sources = {
        DisplayMode.MODE_OUTPUT: [
            item("Speakers (Realtek USB Audio)", 68, True),
            item("Headphones (USB DAC)", 42),
            item("DisplayPort Monitor Audio", 75),
            item("Wireless Headset", 54, muted=True),
            item("HDMI Output", 80),
        ],
        DisplayMode.MODE_INPUT: [
            item("Microphone (USB Audio)", 82, True),
            item("Headset Microphone", 60),
        ],
        DisplayMode.MODE_APPLICATION: [
            item("Spotify", 44), item("Discord", 76),
            item("Browser", 58), item("Game", 85), item("Media Player", 63),
        ],
        DisplayMode.MODE_GAME: [item("Game", 85), item("Voice Chat", 76)],
    }
    controller = SimpleNamespace(
        serial=SimpleNamespace(status="connected" if connected else "waiting",
                               is_connected=connected, port="COM7" if connected else ""),
        audio=SimpleNamespace(get_sessions_for_mode=lambda mode: sources.get(mode, []),
                              set_volume=record("volume"),
                              set_default_device=record("default")),
        preset_service=SimpleNamespace(get_preset_names=lambda: ["Default", "Focus", "Gaming"],
                                       apply_preset=record("preset")),
        obs_service=SimpleNamespace(
            is_connected=True, is_streaming=False, is_recording=False,
            scenes=["Main", "Camera", "Break"], current_scene="Main",
            toggle_streaming=record("stream"), toggle_recording=record("record"),
            toggle_input_mute=record("obs_mute"), switch_scene=record("scene"),
            mic_input="Microphone", desktop_input="Desktop Audio", input_mutes={},
        ),
        media_service=SimpleNamespace(
            cached_snapshot=lambda: SimpleNamespace(
                info=SimpleNamespace(title="Night Drive", artist="Studio Session",
                                     is_playing=True)),
            execute_control=record("media"),
        ),
        _device_connected=connected,
        firmware_updating=False,
        can_update_firmware=connected,
        firmware_version=APP_VERSION if connected else "unknown",
        updates=UpdateCoordinator(),
        active_profile="Default", routing_enabled=True, routing_supported=True,
        ducking_enabled=False, auto_profile_switching=False,
        toggle_routing=record("routing"), toggle_ducking=record("ducking"),
        set_routing_enabled=record("set_routing"),
        set_ducking_enabled=record("set_ducking"),
        open_audio_automation_config=record("rules"), apply_profile=record("profile"),
        open_log_folder=record("logs"), diagnostic_report=lambda: "Visual QA fixture",
        reconnect=record("reconnect"), disconnect=record("disconnect"),
        update_settings=record("settings"),
    )
    return controller, calls


def settle(window, seconds=0.12):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        window.update_idletasks()
        window.update()
        time.sleep(0.01)


def widget_report(window):
    """Record real geometry; CTk's internal drawing primitives are excluded."""
    from customtkinter import CTkBaseClass, ScalingTracker

    rows = []
    root_x, root_y = window.winfo_rootx(), window.winfo_rooty()

    def walk(widget):
        for child in widget.winfo_children():
            if not child.winfo_ismapped():
                if (widget.winfo_ismapped() and child.winfo_manager()
                        and isinstance(child, CTkBaseClass)):
                    rows.append({"class":type(child).__name__, "text":"",
                                 "rect":[child.winfo_x(), child.winfo_y(),
                                         child.winfo_width(), child.winfo_height()],
                                 "parent_rect":[], "outside_parent":False,
                                 "hidden_managed":True, "image_clipped":False})
                continue
            if isinstance(child, CTkBaseClass):
                text = ""
                try:
                    text = str(child.cget("text"))
                except (ValueError, AttributeError, tkinter.TclError):
                    pass
                try:
                    variable = child.cget("textvariable")
                    if variable is not None and hasattr(variable, "get"):
                        text = str(variable.get())
                except (ValueError, AttributeError, tkinter.TclError):
                    pass
                rect = [child.winfo_rootx() - root_x, child.winfo_rooty() - root_y,
                        child.winfo_width(), child.winfo_height()]
                parent = child.master
                parent_rect = [parent.winfo_rootx() - root_x, parent.winfo_rooty() - root_y,
                               parent.winfo_width(), parent.winfo_height()]
                x, y, width, height = rect
                px, py, pw, ph = parent_rect
                outside_parent = x < px - 2 or y < py - 2 or x + width > px + pw + 2 or y + height > py + ph + 2
                row = {"class":type(child).__name__, "text":text,
                       "rect":rect, "parent_rect":parent_rect,
                       "outside_parent":outside_parent,
                       "hidden_managed":False, "image_clipped":False}
                try:
                    image = child.cget("image")
                    if image is not None and hasattr(image, "cget"):
                        size = image.cget("size")
                        scale = ScalingTracker.get_widget_scaling(child)
                        expected = [round(side * scale) for side in size]
                        label = getattr(child, "_image_label", None)
                        if label is None:
                            label = getattr(child, "_label", None)
                        if label is not None and label.winfo_ismapped():
                            label_size = [label.winfo_width(), label.winfo_height()]
                            available = [min(width, label_size[0]), min(height, label_size[1])]
                            row.update(image_size=list(size), image_physical=expected,
                                       image_available=available,
                                       image_clipped=any(need > have + 2 for need, have
                                                         in zip(expected, available)))
                except (ValueError, AttributeError, tkinter.TclError):
                    pass
                rows.append(row)
            walk(child)

    walk(window)
    return rows


def main():
    args = parse_args()
    args.source = args.source.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.version:
        os.environ["VUNMIX_VERSION"] = args.version
    sys.path.insert(0, str(args.source / "desktop"))
    watched = ("gui.py", "fluent_theme.py", "fluent_views.py", "ui_sections.py",
               "connection_ui.py", "clock_preview.py", "clock_font_data.py")

    def source_hashes():
        return {name: hashlib.sha256(path.read_bytes()).hexdigest()
                for name in watched if (path := args.source / "desktop" / name).is_file()}

    initial_hashes = source_hashes()
    ctk = load_ctk()
    if not 0.5 <= args.scaling <= 2.0:
        raise ValueError("QA scaling must be between 0.5 and 2.0")
    ctk.set_widget_scaling(args.scaling)
    ctk.set_window_scaling(args.scaling)
    # Importing media constants on Linux needs only this inert native module;
    # no Windows service implementation is instantiated or called.
    if sys.platform != "win32":
        sys.modules.setdefault("win32gui", ModuleType("win32gui"))
    from config import AppConfig
    from connection_ui import ConnectionSettingsDialog
    from protocol import CLOCK_STYLE_NAMES
    from PIL import ImageGrab
    import tkinter.font as tkfont

    controller, calls = make_controller(args.connected)
    config = AppConfig(com_port="COM7", favorite_apps=["Spotify", "Discord"])
    config.device_settings.clock_style = args.clock_style
    dialog = ConnectionSettingsDialog(config, controller, on_save=lambda *_: None)
    manifest = {"source":str(args.source), "backend":"real Tk/CustomTkinter",
                "source_hashes":initial_hashes, "platform":sys.platform,
                "requested_scaling":args.scaling,
                "sidebar":args.sidebar,
                "initial_clock_style":args.clock_style,
                "ctk_version":ctk.__version__, "fixture_connected":args.connected,
                "captures":[], "callback_errors":[]}
    try:
        with patch("gui.serial.tools.list_ports.comports", return_value=[]):
            dialog.initialize()
        window = dialog._window

        def report_callback_exception(exc_type, value, tb):
            manifest["callback_errors"].append("".join(traceback.format_exception(exc_type, value, tb)))

        window.report_callback_exception = report_callback_exception
        manifest["tk_version"] = str(window.tk.call("info", "patchlevel"))
        manifest["segoe_font_actual"] = tkfont.Font(window, family="Segoe UI", size=12).actual()
        manifest["initial_geometry"] = window.geometry()
        window.deiconify()

        def capture(size, route, suffix=""):
            dialog._last_audio_snapshot = 0.0
            dialog._refresh_control_center()
            settle(window)
            x, y = window.winfo_rootx(), window.winfo_rooty()
            width, height = window.winfo_width(), window.winfo_height()
            filename = f"{size}_{route.lower().replace(' ', '_')}{suffix}.png"
            ImageGrab.grab(bbox=(x, y, x + width, y + height),
                           xdisplay=os.environ.get("DISPLAY")).save(args.output / filename)
            widgets = widget_report(window)
            manifest["captures"].append({"file":filename, "size":[width, height],
                                        "route":route, "widgets":widgets,
                                        "overflow":[row for row in widgets if row["outside_parent"]],
                                        "hidden_managed":[row for row in widgets if row["hidden_managed"]],
                                        "image_clipping":[row for row in widgets if row["image_clipped"]]})
            print(filename, "visible widgets:", len(widgets), "overflow:",
                  sum(row["outside_parent"] for row in widgets), flush=True)

        for size in args.sizes.split(","):
            dialog._sidebar_manual_override = args.sidebar != "auto"
            if args.sidebar != "auto":
                dialog._set_fluent_sidebar_collapsed(args.sidebar == "collapsed")
            window.geometry(f"{size}+0+0")
            settle(window)
            for route in ("Overview", "Audio", "Clock", "Device", "Updates", "Settings"):
                dialog._fluent_navigate(route)
                capture(size, route)
            dialog._fluent_navigate("Audio")
            for page in ("Profiles", "Media / OBS"):
                dialog._fluent_show_audio_page(page)
                dialog._audio_page_switcher.set(page)
                capture(size, "Audio", "_" + page.lower().replace(" / ", "_").replace(" ", "_"))
            dialog._fluent_show_audio_page("Mixer")
            dialog._audio_page_switcher.set("Mixer")
            for source in ("Input", "Applications", "Game Mixer"):
                dialog._fluent_audio_source_changed(source)
                capture(size, "Audio", "_" + source.lower().replace(" ", "_"))
            dialog._fluent_audio_source_changed("Output")

        if args.all_clock_styles:
            window.geometry("1040x680+0+0")
            dialog._fluent_navigate("Clock")
            for index, name in enumerate(CLOCK_STYLE_NAMES):
                dialog._fluent_choose_clock(index)
                capture("1040x680", "Clock", f"_{index:02d}")
    finally:
        if dialog._window is not None:
            dialog._shutdown_from_ui()
        manifest["service_calls"] = calls
        manifest["source_changed_during_capture"] = source_hashes() != initial_hashes
        (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if manifest["callback_errors"]:
        raise RuntimeError("Tk callback errors were recorded in manifest.json")
    if calls:
        raise RuntimeError("Rendering caused unexpected service side effects")
    if manifest["source_changed_during_capture"]:
        raise RuntimeError("UI source changed during capture; rerun against a stable tree")
    if args.assert_layout and any(frame["overflow"] or frame["hidden_managed"] or frame["image_clipping"]
                                  for frame in manifest["captures"]):
        raise RuntimeError("Clipped or hidden managed widgets were recorded in manifest.json")


if __name__ == "__main__":
    main()
