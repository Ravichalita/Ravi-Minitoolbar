import uno
import unohelper
import os
import sys
import json
import traceback
import time
from datetime import datetime
from com.sun.star.task import XJobExecutor, XJob
from com.sun.star.lang import XServiceInfo
from com.sun.star.view import XSelectionChangeListener
from com.sun.star.frame import XDispatchProvider, XDispatch, FeatureStateEvent
from com.sun.star.awt import (
    XMouseListener, XMouseMotionListener, XActionListener, XItemListener,
    XKeyListener, XFocusListener, Point, Size,
)

IMPLEMENTATION_NAME = "org.ravic.minitoolbar.MiniToolbarExtension"
SERVICE_NAMES = ("com.sun.star.task.JobExecutor", "com.sun.star.task.Job", "com.sun.star.frame.ProtocolHandler")
LOG_FILE = ""
CONFIG_FILE = ""


def set_paths(ctx):
    global LOG_FILE, CONFIG_FILE
    if LOG_FILE: return
    try:
        ps = ctx.ServiceManager.createInstanceWithContext("com.sun.star.util.PathSubstitution", ctx)
        user_url = ps.substituteVariables("$(user)", True)
        user_path = uno.fileUrlToSystemPath(user_url)
    except:
        user_path = os.path.expanduser("~")
    LOG_FILE = os.path.join(user_path, "minitoolbar.log")
    CONFIG_FILE = os.path.join(user_path, "minitoolbar_config.json")

RECENT_MOUSE_SECONDS = 3.0
MM_100TH = 0
SYSTEM_WIN32 = 1
MAX_ACCESSIBLE_SEARCH = 60
TOOLBAR_GAP = 6
UI_CLAMP_MARGIN = 4
DRAG_THRESHOLD = 3

_ACTIVE_INSTANCE = None

# Normal layout
N_BTN = 12
N_FONT = 7
N_COMBO_W = 48
N_COMBO_H = 12
N_Y = 2
N_WIDTH = 240
N_HEIGHT = 16
N_SCR_W = 528
N_SCR_H = 34

# Large layout
L_BTN = 17
L_FONT = 9
L_COMBO_W = 62
L_COMBO_H = 16
L_Y = 3
L_WIDTH = 320
L_HEIGHT = 22
L_SCR_W = 704
L_SCR_H = 46

COLOR_PALETTE = [
    0x000000, 0x434343, 0x888888, 0xCCCCCC, 0xFFFFFF, 0xFF0000,
    0xFF9900, 0xFFFF00, 0x00CC00, 0x00CCFF, 0x0066FF, 0x9933FF,
    0xCC0000, 0x996600, 0x009900, 0x006666, 0x003399, 0x660099,
    0xFF9999, 0xFFCC99, 0xFFFF99, 0x99FF99, 0x99CCFF, 0xCC99FF,
]
CPOP_COLS = 6

COMMON_FONTS = [
    "Arial", "Arial Black", "Calibri", "Cambria", "Comic Sans MS",
    "Consolas", "Courier New", "Georgia", "Impact", "Lucida Sans",
    "Palatino Linotype", "Segoe UI", "Tahoma", "Times New Roman",
    "Trebuchet MS", "Verdana",
]

COMMON_SIZES = [
    "6", "7", "8", "9", "10", "10.5", "11", "12", "13", "14", "15",
    "16", "18", "20", "22", "24", "26", "28", "32", "36", "40", "44",
    "48", "54", "60", "66", "72", "80", "96",
]


def log(msg):
    if not LOG_FILE: return
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    except:
        pass


class AL(unohelper.Base, XActionListener):
    def __init__(self, fn):
        self.fn = fn
    def actionPerformed(self, e):
        self.fn(e)
    def disposing(self, e):
        pass


class IL(unohelper.Base, XItemListener):
    def __init__(self, fn):
        self.fn = fn
    def itemStateChanged(self, e):
        self.fn(e)
    def disposing(self, e):
        pass


class FL(unohelper.Base, XFocusListener):
    def __init__(self, fn):
        self.fn = fn
    def focusGained(self, e):
        pass
    def focusLost(self, e):
        self.fn(e)
    def disposing(self, e):
        pass


class MiniToolbarExtension(
    unohelper.Base, XJobExecutor, XJob, XServiceInfo,
    XSelectionChangeListener, XMouseListener, XMouseMotionListener,
    XKeyListener, XDispatchProvider, XDispatch,
):
    def __init__(self, ctx):
        self.ctx = ctx
        set_paths(ctx)
        self.mouse_pos = Point(-1, -1)
        self.mouse_at = 0
        self.dialog = None
        self.color_popup = None
        self.align_popup = None
        self.color_mode = None
        self._lsnr = []
        self.active_docs = {}
        self.last_frame = None
        self._chrome_done = False
        self._busy = False
        self._dragging = False
        self._drag_moved = False
        self._drag_start_screen = Point(0, 0)
        self._drag_start_dialog = Point(0, 0)
        self._drag_control_names = set()
        self._btn_commands = {}
        self._pressed_btn_name = None
        self._last_cursor_source = "none"
        self._cfg = self._load_cfg()
        self._status_listeners = {}
        log("--- v16-custom-click ---")

    # ── Config ──────────────────────────────────────────────────────
    def _load_cfg(self):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.loads(f.read())
        except:
            return {"enabled": False, "large": False}

    def _save_cfg(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                f.write(json.dumps(self._cfg))
        except:
            pass

    def _is_large(self):
        return self._cfg.get("large", False)

    def _scr_w(self):
        try:
            if hasattr(self, "dialog") and self.dialog:
                model = self.dialog.getModel()
                from com.sun.star.util.MeasureUnit import APPFONT
                sz = self.dialog.getPeer().convertSizeToPixel(Size(model.Width, model.Height), APPFONT)
                return sz.Width
        except:
            pass
        return L_SCR_W if self._is_large() else N_SCR_W

    def _scr_h(self):
        try:
            if hasattr(self, "dialog") and self.dialog:
                model = self.dialog.getModel()
                from com.sun.star.util.MeasureUnit import APPFONT
                sz = self.dialog.getPeer().convertSizeToPixel(Size(model.Width, model.Height), APPFONT)
                return sz.Height
        except:
            pass
        return L_SCR_H if self._is_large() else N_SCR_H

    def _half_w(self):
        return (self._scr_w() // 2)

    def _get_scale_factors(self):
        try:
            if hasattr(self, "dialog") and self.dialog:
                from com.sun.star.util.MeasureUnit import APPFONT
                sz = self.dialog.getPeer().convertSizeToPixel(Size(100, 100), APPFONT)
                return sz.Width / 100.0, sz.Height / 100.0
        except:
            pass
        return 2.2, 2.2

    # ── XJobExecutor ────────────────────────────────────────────────
    def trigger(self, args):
        if args == "activate":
            self._cfg["enabled"] = not self._cfg.get("enabled", False)
            self._save_cfg()
            if self._cfg["enabled"]:
                self._register()
                log("ATIVADA")
            else:
                self._unregister()
                self._hide()
                log("DESATIVADA")
        elif args == "toggle_large":
            self._cfg["large"] = not self._cfg.get("large", False)
            self._save_cfg()
            self._destroy_dialog()
            log(f"Icones grandes: {self._cfg['large']}")
            if self._cfg.get("enabled"):
                ctrl = self._get_ctrl()
                if ctrl:
                    sel, text = self._get_text_selection(ctrl)
                    if sel and text:
                        self._show_toolbar(ctrl)
        else:
            if self._cfg.get("enabled"):
                self._register()
                log("Auto-ativada")

    # ── XDispatchProvider ───────────────────────────────────────────
    def queryDispatch(self, url, target_frame_name, search_flags):
        if url.Complete.startswith("org.ravic.minitoolbar.extension:"):
            return self
        return None

    def queryDispatches(self, requests):
        ret = []
        for r in requests:
            ret.append(self.queryDispatch(r.URL, r.TargetFrameName, r.SearchFlags))
        return tuple(ret)

    # ── XDispatch ───────────────────────────────────────────────────
    def dispatch(self, url, args):
        cmd = url.Complete
        log(f"Dispatch command: {cmd}")
        if cmd == "org.ravic.minitoolbar.extension:Enable":
            self._cfg["enabled"] = True
            self._save_cfg()
            self._register()
            log("ATIVADA")
            self._update_all_menu_states()
        elif cmd == "org.ravic.minitoolbar.extension:Disable":
            self._cfg["enabled"] = False
            self._save_cfg()
            self._unregister()
            self._hide()
            log("DESATIVADA")
            self._update_all_menu_states()
        elif cmd == "org.ravic.minitoolbar.extension:LargeIcons":
            self._cfg["large"] = True
            self._save_cfg()
            self._destroy_dialog()
            log("Icones grandes: True")
            self._update_all_menu_states()
            if self._cfg.get("enabled"):
                ctrl = self._get_ctrl()
                if ctrl:
                    sel, text = self._get_text_selection(ctrl)
                    if sel and text:
                        self._show_toolbar(ctrl)
        elif cmd == "org.ravic.minitoolbar.extension:SmallIcons":
            self._cfg["large"] = False
            self._save_cfg()
            self._destroy_dialog()
            log("Icones grandes: False")
            self._update_all_menu_states()
            if self._cfg.get("enabled"):
                ctrl = self._get_ctrl()
                if ctrl:
                    sel, text = self._get_text_selection(ctrl)
                    if sel and text:
                        self._show_toolbar(ctrl)

    def addStatusListener(self, listener, url):
        cmd = url.Complete
        if cmd not in self._status_listeners:
            self._status_listeners[cmd] = []
        self._status_listeners[cmd].append(listener)
        self._notify_listener(listener, url)

    def removeStatusListener(self, listener, url):
        cmd = url.Complete
        if cmd in self._status_listeners:
            try:
                self._status_listeners[cmd].remove(listener)
            except ValueError:
                pass

    def _notify_listener(self, listener, url):
        try:
            state = False
            if url.Complete == "org.ravic.minitoolbar.extension:Enable":
                state = self._cfg.get("enabled", False)
            elif url.Complete == "org.ravic.minitoolbar.extension:Disable":
                state = not self._cfg.get("enabled", False)
            elif url.Complete == "org.ravic.minitoolbar.extension:LargeIcons":
                state = self._cfg.get("large", False)
            elif url.Complete == "org.ravic.minitoolbar.extension:SmallIcons":
                state = not self._cfg.get("large", False)

            event = FeatureStateEvent()
            event.FeatureURL = url
            event.Source = self
            event.IsEnabled = True
            event.State = state
            
            listener.statusChanged(event)
        except Exception as e:
            log(f"Error notifying listener: {e}")

    def _update_all_menu_states(self):
        for cmd, listeners in self._status_listeners.items():
            for listener in list(listeners):
                try:
                    url = uno.createUnoStruct("com.sun.star.util.URL")
                    url.Complete = cmd
                    if ":" in cmd:
                        parts = cmd.split(":", 1)
                        url.Protocol = parts[0] + ":"
                        url.Path = parts[1]
                    else:
                        url.Protocol = ""
                        url.Path = cmd
                    self._notify_listener(listener, url)
                except Exception as e:
                    log(f"Error in _update_all_menu_states: {e}")

    def _destroy_dialog(self):
        self._hide()
        self._hide_color_popup(dispose=True)
        self._hide_align_popup(dispose=True)
        if self.dialog:
            try:
                self.dialog.dispose()
            except:
                pass
            self.dialog = None
            self._chrome_done = False
            self._dragging = False
            self._drag_control_names = set()

    # ── XJob ────────────────────────────────────────────────────────
    def execute(self, args):
        if self._cfg.get("enabled"):
            self._register()
            log("Auto-ativada via XJob")
        return ()

    # ── Listener registration ───────────────────────────────────────
    def _register(self):
        try:
            desktop = self.ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.frame.Desktop", self.ctx)
            doc = desktop.getCurrentComponent()
            if doc and hasattr(doc, "RuntimeUID"):
                uid = doc.RuntimeUID
                if uid not in self.active_docs:
                    ctrl = doc.getCurrentController()
                    ctrl.addSelectionChangeListener(self)
                    frame = ctrl.getFrame()
                    try:
                        frame.getContainerWindow().addMouseListener(self)
                        frame.getComponentWindow().addMouseListener(self)
                    except:
                        pass
                    try:
                        frame.getContainerWindow().addKeyListener(self)
                        frame.getComponentWindow().addKeyListener(self)
                    except:
                        pass
                    self.active_docs[uid] = True
        except:
            log(f"Reg err: {traceback.format_exc()}")

    def _unregister(self):
        try:
            desktop = self.ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.frame.Desktop", self.ctx)
            doc = desktop.getCurrentComponent()
            if doc and hasattr(doc, "RuntimeUID"):
                uid = doc.RuntimeUID
                if uid in self.active_docs:
                    ctrl = doc.getCurrentController()
                    try:
                        ctrl.removeSelectionChangeListener(self)
                    except:
                        pass
                    frame = ctrl.getFrame()
                    try:
                        frame.getContainerWindow().removeMouseListener(self)
                        frame.getComponentWindow().removeMouseListener(self)
                    except:
                        pass
                    try:
                        frame.getContainerWindow().removeKeyListener(self)
                        frame.getComponentWindow().removeKeyListener(self)
                    except:
                        pass
                    del self.active_docs[uid]
        except:
            pass

    # ── XSelectionChangeListener ────────────────────────────────────
    def selectionChanged(self, event):
        try:
            if self._busy:
                return
            self._hide_color_popup()
            self._hide_align_popup()
            ctrl = event.Source
            sel, text = self._get_text_selection(ctrl)
            if sel and text:
                self._show_toolbar(ctrl)
                self._update_button_states(ctrl)
            else:
                self._hide()
        except:
            log(f"Sel err: {traceback.format_exc()}")

    # ── XMouseListener ──────────────────────────────────────────────
    def mouseReleased(self, event):
        if self._dragging:
            was_moved = self._drag_moved
            pressed = self._pressed_btn_name
            self._finish_drag()
            # Only fire button action if the mouse did NOT move (pure click)
            if not was_moved and pressed:
                cmd = self._btn_commands.get(pressed)
                if cmd:
                    log(f"Click detected on btn={pressed} cmd={cmd}")
                    self._on_btn_click(cmd)
            return
        if self._is_toolbar_source(event.Source) or self._is_combo_source(event.Source):
            return
        try:
            self.mouse_pos = self._cursor_screen_point(event)
            self.mouse_at = time.monotonic()
            log("POS mouseReleased "
                f"src={self._source_name(event.Source)} "
                f"local=({getattr(event, 'X', '?')},{getattr(event, 'Y', '?')}) "
                f"screen={self._fmt_pt(self.mouse_pos)} "
                f"via={self._last_cursor_source}")
            ctrl = self._get_ctrl()
            if ctrl:
                sel, text = self._get_text_selection(ctrl)
                if sel and text:
                    self._show_toolbar(ctrl)
        except:
            pass

    def mousePressed(self, event):
        if self._is_combo_source(event.Source):
            return
        if self._is_toolbar_source(event.Source):
            # Record which button was pressed for click detection
            try:
                model = event.Source.getModel()
                self._pressed_btn_name = getattr(model, "Name", "")
            except:
                self._pressed_btn_name = None
            self._start_drag(event)
            return
        try:
            self.mouse_pos = self._cursor_screen_point(event)
            self.mouse_at = time.monotonic()
            log("POS mousePressed "
                f"src={self._source_name(event.Source)} "
                f"local=({getattr(event, 'X', '?')},{getattr(event, 'Y', '?')}) "
                f"screen={self._fmt_pt(self.mouse_pos)} "
                f"via={self._last_cursor_source}")
        except:
            pass
        self._hide()
        self._hide_color_popup()

    def mouseEntered(self, event):
        pass

    def mouseExited(self, event):
        pass

    # ── XMouseMotionListener ────────────────────────────────────────
    def mouseDragged(self, event):
        self._drag_toolbar(event)

    def mouseMoved(self, event):
        pass

    # ── XKeyListener ────────────────────────────────────────────────
    def keyPressed(self, event):
        try:
            from com.sun.star.awt.Key import ESCAPE, RETURN
            if event.KeyCode == ESCAPE:
                log("ESC pressed, closing toolbar")
                self._hide()
                return
            if event.KeyCode == RETURN:
                try:
                    model = event.Source.getModel()
                    name = getattr(model, "Name", "")
                    if name == "SizeCombo":
                        log("Enter pressed in SizeCombo")
                        self._on_size_changed()
                        ctrl = self._get_ctrl()
                        if ctrl:
                            self._update_button_states(ctrl)
                            try:
                                ctrl.getFrame().getComponentWindow().setFocus()
                            except:
                                pass
                    elif name == "FontCombo":
                        log("Enter pressed in FontCombo")
                        self._on_font_changed()
                        ctrl = self._get_ctrl()
                        if ctrl:
                            self._update_button_states(ctrl)
                            try:
                                ctrl.getFrame().getComponentWindow().setFocus()
                            except:
                                pass
                except:
                    pass
        except Exception as ex:
            log(f"Key press err: {ex}")

    def keyReleased(self, event):
        pass

    def _start_drag(self, event):
        if not self.dialog:
            return
        try:
            screen = self._cursor_screen_point(event)
            pos = self.dialog.getPosSize()
            self._dragging = True
            self._drag_moved = False
            self._drag_start_screen = screen
            self._drag_start_dialog = Point(pos.X, pos.Y)
            self._hide_color_popup()
            self._hide_align_popup()
        except:
            self._dragging = False

    def _drag_toolbar(self, event):
        if not self._dragging or not self.dialog:
            return
        try:
            screen = self._cursor_screen_point(event)
            dx = screen.X - self._drag_start_screen.X
            dy = screen.Y - self._drag_start_screen.Y
            if abs(dx) >= DRAG_THRESHOLD or abs(dy) >= DRAG_THRESHOLD:
                self._drag_moved = True
            target = Point(self._drag_start_dialog.X + dx,
                           self._drag_start_dialog.Y + dy)
            target = self._clamp(target, self.last_frame)
            self.dialog.setPosSize(
                int(target.X), int(target.Y), self._scr_w(), self._scr_h(), 15)
        except:
            pass

    def _finish_drag(self):
        self._dragging = False
        self._drag_moved = False
        self._pressed_btn_name = None

    def _is_combo_source(self, source):
        if not source:
            return False
        try:
            model = source.getModel()
            name = getattr(model, "Name", "")
            return name in ("FontCombo", "SizeCombo")
        except:
            return False

    def _is_toolbar_source(self, source):
        if not self.dialog or not source:
            return False
        try:
            if source == self.dialog:
                return True
        except:
            pass
        try:
            model = source.getModel()
            name = getattr(model, "Name", "")
            return name in self._drag_control_names
        except:
            return False

    def _fmt_pt(self, p):
        if not p:
            return "None"
        try:
            return f"({int(p.X)},{int(p.Y)})"
        except:
            return str(p)

    def _fmt_rect(self, r):
        if not r:
            return "None"
        try:
            return f"({int(r[0])},{int(r[1])},{int(r[2])},{int(r[3])})"
        except:
            return str(r)

    def _source_name(self, source):
        try:
            model = source.getModel()
            name = getattr(model, "Name", "")
            if name:
                return name
        except:
            pass
        try:
            return source.getImplementationName()
        except:
            pass
        try:
            return source.__class__.__name__
        except:
            return "unknown"

    def _cursor_screen_point(self, event=None):
        if event:
            p = self._event_hwnd_screen_point(event)
            if p:
                self._last_cursor_source = "event_hwnd"
                return p
            try:
                origin = self._screen_origin(event.Source)
                if origin:
                    self._last_cursor_source = "event_origin"
                    return Point(origin.X + event.X, origin.Y + event.Y)
            except:
                pass
            try:
                self._last_cursor_source = "event_local"
                return Point(event.X, event.Y)
            except:
                pass
        self._last_cursor_source = "zero"
        return Point(0, 0)

    def _event_hwnd_screen_point(self, event):
        if not sys.platform.startswith("win"):
            return None
        try:
            import ctypes
            from ctypes import wintypes
            h = self._get_handle(event.Source)
            if not h:
                return None

            class PT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            pt = PT(int(event.X), int(event.Y))
            if ctypes.windll.user32.ClientToScreen(
                    wintypes.HWND(h), ctypes.byref(pt)):
                return Point(int(pt.x), int(pt.y))
        except:
            pass
        return None

    def _win32_cursor_logical_point(self):
        if not sys.platform.startswith("win"):
            return None
        try:
            import ctypes

            class PT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            pt = PT()
            if not ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                return None
            wr = self._win32_work_area()
            lr = self._toolkit_work_area()
            if wr and lr and wr[2] > 0 and wr[3] > 0:
                x = lr[0] + (int(pt.x) - wr[0]) * (lr[2] / float(wr[2]))
                y = lr[1] + (int(pt.y) - wr[1]) * (lr[3] / float(wr[3]))
                return Point(int(x), int(y))
            return Point(int(pt.x), int(pt.y))
        except:
            return None

    def _win32_work_area(self):
        if not sys.platform.startswith("win"):
            return None
        try:
            import ctypes
            from ctypes import wintypes
            SPI_GETWORKAREA = 0x0030
            r = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(
                    SPI_GETWORKAREA, 0, ctypes.byref(r), 0):
                return (int(r.left), int(r.top),
                        int(r.right - r.left),
                        int(r.bottom - r.top))
        except:
            pass
        return None

    def _toolkit_work_area(self):
        try:
            tk = self.ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.awt.Toolkit", self.ctx)
            a = tk.getWorkArea()
            return (int(a.X), int(a.Y), int(a.Width), int(a.Height))
        except:
            return None

    # ── Selection helpers ───────────────────────────────────────────
    def _get_ctrl(self):
        try:
            d = self.ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.frame.Desktop", self.ctx)
            doc = d.getCurrentComponent()
            if doc:
                return doc.getCurrentController()
        except:
            pass
        return None

    def _get_text_selection(self, ctrl):
        try:
            sel = ctrl.Model.getCurrentSelection()
            if not sel or not hasattr(sel, "supportsService"):
                return None, ""
            if not sel.supportsService("com.sun.star.text.TextRanges"):
                return None, ""
            if sel.getCount() <= 0:
                return None, ""
            parts = []
            for i in range(sel.getCount()):
                try:
                    p = sel.getByIndex(i).getString()
                    if p:
                        parts.append(p)
                except:
                    pass
            t = "\n".join(parts).strip()
            return (sel, t) if t else (None, "")
        except:
            return None, ""

    # ── Screen origin ───────────────────────────────────────────────
    def _screen_origin(self, obj):
        o = self._origin_hwnd(obj)
        if o:
            return o
        try:
            return obj.getAccessibleContext().getLocationOnScreen()
        except:
            pass
        try:
            return obj.getLocationOnScreen()
        except:
            pass
        try:
            p = obj.getPosSize()
            return Point(p.X, p.Y)
        except:
            pass
        return self._origin_hwnd(obj)

    def _origin_hwnd(self, obj):
        if not sys.platform.startswith("win"):
            return None
        h = self._get_handle(obj)
        if not h:
            return None
        try:
            import ctypes
            from ctypes import wintypes

            class PT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            pt = PT(0, 0)
            if ctypes.windll.user32.ClientToScreen(
                    wintypes.HWND(h), ctypes.byref(pt)):
                return Point(int(pt.x), int(pt.y))
        except:
            pass
        return None

    def _get_handle(self, obj):
        if not obj:
            return None
        for c in (obj,):
            try:
                h = c.getWindowHandle((), SYSTEM_WIN32)
                if isinstance(h, (tuple, list)) and h:
                    h = h[0]
                return int(h)
            except:
                pass
        try:
            h = obj.getPeer().getWindowHandle((), SYSTEM_WIN32)
            if isinstance(h, (tuple, list)) and h:
                h = h[0]
            return int(h)
        except:
            return None

    # ── Toolbar positioning ─────────────────────────────────────────
    def _show_toolbar(self, ctrl):
        try:
            # Diagnostics to inspect Zoom and Scroll
            try:
                vs = ctrl.getViewSettings()
                log("DIAG: ViewSettings:")
                for p in ("ZoomType", "ZoomValue", "ShowHoriRuler", "ShowVertRuler"):
                    if hasattr(vs, p):
                        log(f"DIAG:   {p}={getattr(vs, p)}")
            except Exception as ex:
                log(f"DIAG: failed to read ViewSettings: {ex}")

            try:
                vd = ctrl.getViewData()
                log(f"DIAG: ViewData={vd}")
                if hasattr(vd, "getCount"):
                    for idx in range(vd.getCount()):
                        item = vd.getByIndex(idx)
                        log(f"DIAG: ViewData[{idx}]={item}")
                        try:
                            # If it's a sequence of PropertyValues
                            for pv in item:
                                log(f"DIAG:   {pv.Name}={pv.Value}")
                        except:
                            pass
            except Exception as ex:
                log(f"DIAG: failed to read ViewData: {ex}")

            frame = ctrl.getFrame()
            self.last_frame = frame
            self._ensure_dialog()
            self._update_font_combo(ctrl)
            self._update_size_combo(ctrl)
            self._update_button_states(ctrl)

            a11y_target = self._target_a11y(ctrl)
            target = self._normalize_target(a11y_target, frame)
            
            mouse_target = None
            view_target = None
            fallback_target = None

            if not target:
                mouse_target = self._target_mouse(ctrl)
                target = mouse_target
            if not target:
                view_target = self._target_view_cursor(ctrl)
                target = view_target
            if not target:
                fallback_target = self._target_fallback(frame)
                target = fallback_target

            raw_target = target
            bounds = self._frame_ui_rect(frame)
            work = self._toolkit_work_area()
            target = self._clamp(target, frame)
            sw, sh = self._scr_w(), self._scr_h()
            log("POS show "
                f"mouse_pos={self._fmt_pt(self.mouse_pos)} "
                f"mouse_target={self._fmt_pt(mouse_target)} "
                f"view_target={self._fmt_pt(view_target)} "
                f"a11y_target={self._fmt_pt(a11y_target)} "
                f"fallback_target={self._fmt_pt(fallback_target)} "
                f"raw={self._fmt_pt(raw_target)} "
                f"bounds={self._fmt_rect(bounds)} "
                f"work={self._fmt_rect(work)} "
                f"final={self._fmt_pt(target)} "
                f"size=({sw},{sh})")
            self.dialog.setPosSize(int(target.X), int(target.Y), sw, sh, 15)
            self.dialog.setVisible(True)
            if not self._chrome_done:
                self._remove_chrome("MiniToolbar", sw, sh)
                self._chrome_done = True
            try:
                frame.getComponentWindow().setFocus()
            except:
                pass
        except:
            log(f"Show err: {traceback.format_exc()}")

    def _get_accessible_context(self, win):
        if not win:
            return None
        try:
            if hasattr(win, "getAccessibleContext"):
                acc = win.getAccessibleContext()
                if acc:
                    return acc
        except:
            pass
        try:
            import uno
            # Query XAccessible interface
            x_acc = win.queryInterface(uno.getClass("com.sun.star.accessibility.XAccessible"))
            if x_acc:
                acc = x_acc.getAccessibleContext()
                if acc:
                    return acc
        except:
            pass
        return None

    def _target_a11y(self, ctrl):
        try:
            log("a11y: Start method")
            frame = ctrl.getFrame()
            if not frame:
                log("a11y: frame is None")
                return None
            
            # Try to get accessible context from getComponentWindow first
            win = frame.getComponentWindow()
            acc = self._get_accessible_context(win)
            if acc:
                log(f"a11y: obtained acc from getComponentWindow: {acc}")
            else:
                log("a11y: failed to get acc from getComponentWindow, trying getContainerWindow")
                win = frame.getContainerWindow()
                acc = self._get_accessible_context(win)
                if acc:
                    log(f"a11y: obtained acc from getContainerWindow: {acc}")
                
            if not acc:
                log("a11y: acc is None, returning")
                return None
            
            try:
                cc = acc.getAccessibleChildCount()
                log(f"a11y: acc child count is {cc}")
            except Exception as ex:
                log(f"a11y: getAccessibleChildCount failed: {ex}")
            
            delta = self._a11y_screen_delta(win, acc)
            log(f"a11y: delta calculated: {self._fmt_pt(delta)}")
            
            # DFS search under the accessible tree with menu/toolbar pruning
            selected_node, visits = self._find_selected_a11y_node(acc, 0, 300)
            log(f"a11y DFS search: visited {visits} nodes, found={selected_node is not None}")
            
            if selected_node:
                p = self._a11y_pos(selected_node, delta)
                log(f"a11y: pos calculated: {self._fmt_pt(p)}")
                if p:
                    return p
            else:
                log("a11y: selected node not found in tree")
        except Exception as ex:
            log(f"a11y DFS err: {traceback.format_exc()}")
        return None

    def _find_selected_a11y_node(self, obj, visited_count=0, max_visits=300):
        if visited_count >= max_visits:
            return None, visited_count
        visited_count += 1
        
        # Determine if we should prune this branch (e.g. menus, toolbars, scrollbars)
        try:
            role = obj.getAccessibleRole()
            # Prune typical menu, toolbar, status bar, scrollbar subtrees:
            # 35: MENU_BAR, 63: TOOL_BAR, 59: STATUS_BAR, 51: SCROLL_BAR, 34: MENU, 40: POPUP_MENU
            if role in (34, 35, 40, 51, 59, 63):
                return None, visited_count
        except:
            pass
        
        # Check if this node has selected text
        try:
            s = obj.getSelectedText()
            if s and s.strip():
                return obj, visited_count
        except:
            pass
            
        # Recurse into children
        try:
            count = obj.getAccessibleChildCount()
            for i in range(count):
                try:
                    child = obj.getAccessibleChild(i)
                    if child:
                        try:
                            ctx = child.getAccessibleContext()
                        except:
                            ctx = child
                        if ctx:
                            found, visited_count = self._find_selected_a11y_node(ctx, visited_count, max_visits)
                            if found:
                                return found, visited_count
                except:
                    pass
        except:
            pass
            
        return None, visited_count

    def _a11y_screen_delta(self, win, acc):
        try:
            r = self._screen_rect(win)
            o = acc.getLocationOnScreen()
            if not r or not o:
                return Point(0, 0)
            dx = r[0] - o.X if o.X < r[0] - 16 else 0
            dy = r[1] - o.Y if o.Y < r[1] - 16 else 0
            return Point(int(dx), int(dy))
        except:
            return Point(0, 0)

    def _a11y_pos(self, obj, delta=None):
        try:
            s, e = int(obj.getSelectionStart()), int(obj.getSelectionEnd())
            cnt = int(obj.getCharacterCount())
            if cnt <= 0 or s == e:
                return None
                
            start_idx = max(0, min(min(s, e), cnt - 1))
            end_idx = max(0, min(max(s, e) - 1, cnt - 1))
            
            r_start = obj.getCharacterBounds(start_idx)
            r_end = obj.getCharacterBounds(end_idx)
            
            try:
                o = obj.getLocationOnScreen()
            except:
                return None
                
            if delta:
                o = Point(o.X + delta.X, o.Y + delta.Y)
                
            # If selection is on the same line, center the toolbar horizontally under the selection
            if abs(r_start.Y - r_end.Y) < 5:
                sel_center_x = o.X + r_start.X + (r_end.X + r_end.Width - r_start.X) // 2
                x = sel_center_x - self._half_w()
                y = o.Y + r_start.Y + max(1, r_start.Height) + TOOLBAR_GAP
            else:
                # Multi-line selection: position under the first line's selection start
                x = o.X + r_start.X + max(1, r_start.Width // 2) - self._half_w()
                y = o.Y + r_start.Y + max(1, r_start.Height) + TOOLBAR_GAP
                
            return Point(x, y)
        except:
            return None

    def _target_view_cursor(self, ctrl):
        try:
            vc = ctrl.getViewCursor()
            if not vc or not hasattr(vc, "getPosition"):
                return None
            p = vc.getPosition()
            
            # Retrieve Zoom Factor dynamically from view settings
            zoom_factor = 1.0
            try:
                vs = ctrl.getViewSettings()
                zoom = getattr(vs, "ZoomValue", 100)
                zoom_factor = zoom / 100.0
            except:
                pass
            
            # Convert 1/100 mm to screen pixels (~96 DPI) and scale by zoom factor
            px_x = int((p.X / 26.46) * zoom_factor)
            px_y = int((p.Y / 26.46) * zoom_factor)
            
            # Scale visual line height by zoom factor
            lh = int(self._line_h(ctrl) * zoom_factor)
            
            bounds = self._frame_ui_rect(ctrl.getFrame())
            if not bounds:
                return Point(px_x - self._half_w(),
                            px_y + lh + TOOLBAR_GAP + 160)
            
            # Translate local document coordinates to absolute screen coordinates
            # by adding the window's screen origin (bounds[0], bounds[1])
            # and adding +160 pixels to calibrate for formatting toolbars, rulers, and page margins.
            shifted = Point(bounds[0] + px_x - self._half_w(),
                            bounds[1] + px_y + lh + TOOLBAR_GAP + 160)
            return shifted
        except:
            return None

    def _target_mouse(self, ctrl):
        if self.mouse_pos.X < 0:
            return None
        if time.monotonic() - self.mouse_at > RECENT_MOUSE_SECONDS:
            return None
        lh = self._line_h(ctrl)
        return Point(self.mouse_pos.X - self._half_w(),
                     self.mouse_pos.Y + lh + TOOLBAR_GAP)

    def _target_win32(self, ctrl):
        if not sys.platform.startswith("win"):
            return None
        try:
            import ctypes

            class PT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            pt = PT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                lh = self._line_h(ctrl)
                return Point(int(pt.x) - self._half_w(),
                             int(pt.y) + lh + TOOLBAR_GAP)
        except:
            pass
        return None

    def _target_fallback(self, frame):
        r = self._frame_ui_rect(frame)
        if r:
            return Point(r[0] + 200, r[1] + 200)
        o = self._screen_origin(frame.getComponentWindow())
        if o:
            return Point(o.X + 200, o.Y + 200)
        return Point(200, 200)

    def _clamp(self, target, frame=None, width=None, height=None):
        if not target:
            target = Point(200, 200)
        sw = width if width is not None else self._scr_w()
        sh = height if height is not None else self._scr_h()
        bounds = self._frame_ui_rect(frame or self.last_frame)
        if bounds and self._target_center_in_rect(target, bounds, sw):
            return self._clamp_to_rect(target, bounds, sw, sh)
        try:
            tk = self.ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.awt.Toolkit", self.ctx)
            a = tk.getWorkArea()
            return self._clamp_to_rect(target, (a.X, a.Y, a.Width, a.Height),
                                       sw, sh, 0)
        except:
            pass
        return target

    def _normalize_target(self, target, frame=None):
        if not target:
            return target
        bounds = self._frame_ui_rect(frame or self.last_frame)
        if not bounds:
            return target
        sw = self._scr_w()
        if self._target_center_in_rect(target, bounds, sw):
            return target
        for ox, oy in self._frame_offsets(frame or self.last_frame):
            candidate = Point(target.X + ox, target.Y + oy)
            if self._target_center_in_rect(candidate, bounds, sw):
                return candidate
        return target

    def _target_center_in_rect(self, target, rect, width):
        x = target.X + width // 2
        y = target.Y
        return (rect[0] - 8 <= x <= rect[0] + rect[2] + 8 and
                rect[1] - 8 <= y <= rect[1] + rect[3] + 8)

    def _frame_offsets(self, frame=None):
        offsets = []
        if not frame:
            return offsets
        for getter in ("getComponentWindow", "getContainerWindow"):
            try:
                r = self._screen_rect(getattr(frame, getter)())
                if r:
                    offsets.append((r[0], r[1]))
            except:
                pass
        seen = set()
        unique = []
        for offset in offsets:
            if offset not in seen:
                unique.append(offset)
                seen.add(offset)
        return unique

    def _clamp_to_rect(self, target, rect, width, height,
                       margin=UI_CLAMP_MARGIN):
        x0 = int(rect[0]) + margin
        y0 = int(rect[1]) + margin
        x1 = int(rect[0] + rect[2]) - margin - width
        y1 = int(rect[1] + rect[3]) - margin - height
        if x1 < x0:
            x1 = x0
        if y1 < y0:
            y1 = y0
        x = max(x0, min(int(target.X), x1))
        y = max(y0, min(int(target.Y), y1))
        return Point(int(x), int(y))

    def _frame_ui_rect(self, frame=None):
        if not frame:
            frame = self.last_frame
        if not frame:
            return None
        for getter in ("getComponentWindow", "getContainerWindow"):
            try:
                win = getattr(frame, getter)()
                r = self._screen_rect(win)
                if r and r[2] > 0 and r[3] > 0:
                    return r
            except:
                pass
        if sys.platform.startswith("win"):
            try:
                win = frame.getContainerWindow()
                r = self._top_window_rect(win)
                if r and r[2] > 0 and r[3] > 0:
                    return r
            except:
                pass
        return None

    def _top_window_rect(self, obj):
        h = self._get_handle(obj)
        if not h:
            return None
        try:
            import ctypes
            from ctypes import wintypes
            u32 = ctypes.windll.user32
            GA_ROOT = 2
            root = u32.GetAncestor(wintypes.HWND(h), GA_ROOT)
            if not root:
                root = h
            r = wintypes.RECT()
            if u32.GetWindowRect(wintypes.HWND(root), ctypes.byref(r)):
                return (int(r.left), int(r.top),
                        int(r.right - r.left),
                        int(r.bottom - r.top))
        except:
            return None

    def _screen_rect(self, obj):
        if not obj:
            return None
        r = self._client_rect_hwnd(obj)
        if r:
            return r
        try:
            p = obj.getPosSize()
            o = self._screen_origin(obj)
            if o:
                return (int(o.X), int(o.Y), int(p.Width), int(p.Height))
            return (int(p.X), int(p.Y), int(p.Width), int(p.Height))
        except:
            pass
        try:
            acc = obj.getAccessibleContext()
            o = acc.getLocationOnScreen()
            s = acc.getSize()
            return (int(o.X), int(o.Y), int(s.Width), int(s.Height))
        except:
            pass
        if sys.platform.startswith("win"):
            h = self._get_handle(obj)
            if h:
                try:
                    import ctypes
                    from ctypes import wintypes
                    r = wintypes.RECT()
                    if ctypes.windll.user32.GetWindowRect(
                            wintypes.HWND(h), ctypes.byref(r)):
                        return (int(r.left), int(r.top),
                                int(r.right - r.left),
                                int(r.bottom - r.top))
                except:
                    pass
        return None

    def _client_rect_hwnd(self, obj):
        if not sys.platform.startswith("win"):
            return None
        h = self._get_handle(obj)
        if not h:
            return None
        try:
            import ctypes
            from ctypes import wintypes
            r = wintypes.RECT()
            if not ctypes.windll.user32.GetClientRect(
                    wintypes.HWND(h), ctypes.byref(r)):
                return None

            class PT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            pt = PT(0, 0)
            if not ctypes.windll.user32.ClientToScreen(
                    wintypes.HWND(h), ctypes.byref(pt)):
                return None
            return (int(pt.x), int(pt.y),
                    int(r.right - r.left), int(r.bottom - r.top))
        except:
            return None

    def _line_h(self, ctrl):
        try:
            vc = ctrl.getViewCursor()
            h = getattr(vc, "CharHeight", 12)
            fx, fy = self._get_scale_factors()
            return int(h * 1.33 * fy)
        except:
            pass
        return 20

    # ── Dialog creation ─────────────────────────────────────────────
    def _ensure_dialog(self):
        if self.dialog:
            return
        lg = self._is_large()
        BS = L_BTN if lg else N_BTN
        FH = L_FONT if lg else N_FONT
        CW = L_COMBO_W if lg else N_COMBO_W
        CH = L_COMBO_H if lg else N_COMBO_H
        DW = L_WIDTH if lg else N_WIDTH
        DH = L_HEIGHT if lg else N_HEIGHT
        YY = L_Y if lg else N_Y
        GAP = 2
        CSW = 28 if lg else 22  # Font size combo width

        smgr = self.ctx.ServiceManager
        model = smgr.createInstanceWithContext(
            "com.sun.star.awt.UnoControlDialogModel", self.ctx)
        model.Width = DW
        model.Height = DH
        model.BackgroundColor = 0x2B2B2B
        model.Title = "MiniToolbar"
        try:
            model.Closeable = False
            model.Moveable = False
            model.Sizeable = False
        except:
            pass

        self.dialog = smgr.createInstanceWithContext(
            "com.sun.star.awt.UnoControlDialog", self.ctx)
        self.dialog.setModel(model)

        # Font combo
        cm = model.createInstance("com.sun.star.awt.UnoControlComboBoxModel")
        cm.Name = "FontCombo"
        cm.PositionX = 1
        cm.PositionY = YY
        cm.Width = CW
        cm.Height = CH
        cm.FontHeight = FH
        cm.Dropdown = True
        cm.LineCount = 12
        cm.StringItemList = tuple(self._get_fonts())
        model.insertByName("FontCombo", cm)

        # Font Size combo
        csm = model.createInstance("com.sun.star.awt.UnoControlComboBoxModel")
        csm.Name = "SizeCombo"
        csm.PositionX = 1 + CW + GAP
        csm.PositionY = YY
        csm.Width = CSW
        csm.Height = CH
        csm.FontHeight = FH
        csm.Dropdown = True
        csm.LineCount = 12
        csm.StringItemList = tuple(COMMON_SIZES)
        model.insertByName("SizeCombo", csm)

        # Button definitions: (name, label, cmd_or_action, bold)
        # Using semiotics: up/down arrows for size, Proposta A alignment symbol, ab highlighted block
        btns = [
            ("Down", "A\u25BE", ".uno:Shrink", False),
            ("Up",   "A\u25B4", ".uno:Grow",   False),
            ("Bold", "B",       ".uno:Bold",   True),
            ("Ital", "I",       ".uno:Italic", False),
            ("Undr", "U",       ".uno:Underline", False),
            ("Strk", "S",       ".uno:Strikeout", False),
            ("Sup",  "x\u00B2", ".uno:SuperScript", False),
            ("Sub",  "x\u2082", ".uno:SubScript", False),
            ("Align", "|\u2261", "color:align", False),  # Proposta A: |≡
            ("Fcol", "A\u0332", "color:font",  False),
            ("Hlit", "ab",      "color:highlight", False),
            ("Clr",  "\u2715",  ".uno:ResetAttributes", False),
        ]
        x = 1 + CW + GAP + CSW + GAP
        for name, label, cmd, bold in btns:
            # Group gaps for premium spacing (Size, Style, Align, Color/Reset)
            if name in ("Bold", "Align", "Fcol"):
                x += 3
            self._add_btn(model, name, label, x, YY, BS, cmd, FH, bold)
            x += BS + 1

        tk = smgr.createInstanceWithContext("com.sun.star.awt.Toolkit", self.ctx)
        self.dialog.createPeer(tk, None)

        # Font combo listeners
        cc = self.dialog.getControl("FontCombo")
        il = IL(lambda e: self._on_font_changed())
        self._lsnr.append(il)
        cc.addItemListener(il)
        al = AL(lambda e: self._on_font_changed())
        self._lsnr.append(al)
        cc.addActionListener(al)
        f_fl = FL(lambda e: self._on_font_changed())
        self._lsnr.append(f_fl)
        cc.addFocusListener(f_fl)
        cc.addKeyListener(self)

        # Font Size combo listeners
        sc = self.dialog.getControl("SizeCombo")
        sil = IL(lambda e: self._on_size_changed())
        self._lsnr.append(sil)
        sc.addItemListener(sil)
        sal = AL(lambda e: self._on_size_changed())
        self._lsnr.append(sal)
        sc.addActionListener(sal)
        s_fl = FL(lambda e: self._on_size_changed())
        self._lsnr.append(s_fl)
        sc.addFocusListener(s_fl)
        sc.addKeyListener(self)

        # Button commands mapping (for custom click detection via mousePressed+mouseReleased)
        for name, label, cmd, bold in btns:
            self._btn_commands[name] = cmd
        # NOTE: No addActionListener on buttons — clicks are handled
        # entirely via mousePressed/mouseReleased to prevent spurious
        # activations after dragging the toolbar.
        self._install_toolbar_drag(btns)

    def _install_toolbar_drag(self, btns):
        names = [name for name, label, cmd, bold in btns]
        self._drag_control_names = set(names)
        controls = [self.dialog]
        for name in names:
            try:
                c = self.dialog.getControl(name)
                if c:
                    controls.append(c)
            except:
                pass
        for c in controls:
            try:
                c.addMouseListener(self)
            except:
                pass
            try:
                c.addMouseMotionListener(self)
            except:
                pass
            try:
                c.addKeyListener(self)
            except:
                pass

    def _update_font_combo(self, ctrl):
        if not self.dialog:
            return
        try:
            vc = ctrl.getViewCursor()
            fn = getattr(vc, "CharFontName", "")
            if fn:
                cb = self.dialog.getControl("FontCombo")
                if cb:
                    cb.setText(fn)
        except:
            pass

    def _get_fonts(self):
        try:
            ctrl = self._get_ctrl()
            if ctrl:
                try:
                    descs = ctrl.getFrame().getContainerWindow().getFontDescriptors()
                    names = sorted(set(d.Name for d in descs if d.Name))
                    if len(names) > 5:
                        return names
                except:
                    pass
        except:
            pass
        return COMMON_FONTS

    def _add_btn(self, model, name, label, x, y, size, cmd, fh, bold=False):
        btn = model.createInstance("com.sun.star.awt.UnoControlButtonModel")
        btn.Name = name
        btn.Label = label
        btn.PositionX = x
        btn.PositionY = y
        btn.Width = size
        btn.Height = size
        btn.FontHeight = fh
        btn.BackgroundColor = 0x3C3C3C
        btn.TextColor = 0xFFFFFF
        
        # Semiotics: format the button text using its respective character formatting
        try:
            if name == "Bold":
                btn.FontWeight = 150.0  # com.sun.star.awt.FontWeight.BOLD
            elif name == "Ital":
                from com.sun.star.awt.FontSlant import ITALIC
                btn.FontSlant = ITALIC
            elif name == "Undr":
                btn.FontUnderline = 1   # com.sun.star.awt.FontUnderline.SINGLE
            elif name == "Strk":
                btn.FontStrikeout = 1   # com.sun.star.awt.FontStrikeout.SINGLE
        except:
            pass
            
        tooltips = {
            "Down": "Diminuir tamanho da fonte",
            "Up": "Aumentar tamanho da fonte",
            "Bold": "Negrito",
            "Ital": "Itálico",
            "Undr": "Sublinhado",
            "Strk": "Tachado",
            "Sup": "Sobrescrito",
            "Sub": "Subscrito",
            "Align": "Alinhamento do parágrafo",
            "Fcol": "Cor da fonte",
            "Hlit": "Cor do realce",
            "Clr": "Limpar formatação"
        }
        try:
            btn.HelpText = tooltips.get(name, "")
        except:
            pass
        model.insertByName(name, btn)

    def _on_btn_click(self, cmd):
        if cmd == "color:align":
            self._show_align_popup()
        elif cmd == "color:font":
            self._show_color_popup("font")
        elif cmd == "color:highlight":
            self._show_color_popup("highlight")
        else:
            self._dispatch_cmd(cmd)
            # Update to reflect any formatting changes (like size/bold/italic state) immediately
            ctrl = self._get_ctrl()
            if ctrl:
                self._update_font_combo(ctrl)
                self._update_size_combo(ctrl)
                self._update_button_states(ctrl)

    def _update_button_states(self, ctrl):
        if not self.dialog:
            return
        try:
            self._update_size_combo(ctrl)
            vc = ctrl.getViewCursor()
            is_bold = getattr(vc, "CharWeight", 100) > 110
            is_ital = getattr(vc, "CharPosture", 0) == 1
            is_undr = getattr(vc, "CharUnderline", 0) > 0
            is_strk = getattr(vc, "CharStrikeout", 0) > 0
            esc = getattr(vc, "CharEscapement", 0)
            is_sup = esc > 0
            is_sub = esc < 0
            
            align = 0
            try:
                align = getattr(vc, "ParaAdjust", 0)
            except:
                pass
            is_lft = align == 0
            is_rgt = align == 1
            is_ctr = align == 3
            is_jst = align == 2
            
            # Semiotics: Dynamic alignment icon based on state (Proposta A)
            align_symbol = "|\u2261"
            if is_ctr: align_symbol = " \u2261 "
            elif is_rgt: align_symbol = "\u2261|"
            elif is_jst: align_symbol = "|\u2261|"
            
            try:
                align_btn = self.dialog.getControl("Align")
                if align_btn:
                    align_btn.getModel().Label = align_symbol
                    # Highlight if alignment is not default Left
                    align_btn.getModel().BackgroundColor = 0x4A90E2 if not is_lft else 0x3C3C3C
            except:
                pass

            states = {
                "Bold": is_bold,
                "Ital": is_ital,
                "Undr": is_undr,
                "Strk": is_strk,
                "Sup": is_sup,
                "Sub": is_sub
            }
            for btn_name, active in states.items():
                try:
                    btn = self.dialog.getControl(btn_name)
                    if btn:
                        model = btn.getModel()
                        model.BackgroundColor = 0x4A90E2 if active else 0x3C3C3C
                except:
                    pass
                    
            # Font Color indicator (Fcol)
            try:
                fcol_btn = self.dialog.getControl("Fcol")
                if fcol_btn:
                    fcol_model = fcol_btn.getModel()
                    color = getattr(vc, "CharColor", -1)
                    if color == -1 or color is None:
                        color = 0x000000
                    r = (color >> 16) & 0xFF
                    g = (color >> 8) & 0xFF
                    b = color & 0xFF
                    lum = 0.299 * r + 0.587 * g + 0.114 * b
                    fcol_model.TextColor = color
                    # Dynamic contrast background
                    if lum > 128:
                        fcol_model.BackgroundColor = 0x1F1F1F
                    else:
                        fcol_model.BackgroundColor = 0xE0E0E0
            except:
                pass

            # Highlight Color indicator (Hlit)
            try:
                hlit_btn = self.dialog.getControl("Hlit")
                if hlit_btn:
                    hlit_model = hlit_btn.getModel()
                    bg_color = getattr(vc, "CharBackColor", -1)
                    is_trans = getattr(vc, "CharBackTransparent", True)
                    if is_trans or bg_color == -1 or bg_color is None:
                        hlit_model.BackgroundColor = 0x3C3C3C
                        hlit_model.TextColor = 0xFFFFFF
                    else:
                        hlit_model.BackgroundColor = bg_color
                        r = (bg_color >> 16) & 0xFF
                        g = (bg_color >> 8) & 0xFF
                        b = bg_color & 0xFF
                        bg_lum = 0.299 * r + 0.587 * g + 0.114 * b
                        hlit_model.TextColor = 0x000000 if bg_lum > 128 else 0xFFFFFF
            except:
                pass
        except:
            pass

    def _show_align_popup(self):
        self._hide_color_popup()
        self._ensure_align_popup()
        
        lg = self._is_large()
        BS = L_BTN if lg else N_BTN
        
        # 4 buttons horizontally
        pw = 4 + 4 * BS + 3
        ph = BS + 4

        # Position under Align button on main toolbar
        tb = self.dialog.getPosSize()
        fx, fy = self._get_scale_factors()
        scr_pw = int(pw * fx)
        scr_ph = int(ph * fy)

        btn = self.dialog.getControl("Align")
        if btn:
            btn_pos = btn.getPosSize()
            pop_x = tb.X + btn_pos.X - (scr_pw - btn_pos.Width) // 2
        else:
            pop_x = tb.X

        pop_y = tb.Y + tb.Height + 2

        pos = self._clamp(Point(pop_x, pop_y), self.last_frame,
                          scr_pw, scr_ph)
        pop_x, pop_y = pos.X, pos.Y

        self.align_popup.setPosSize(pop_x, pop_y, scr_pw, scr_ph, 15)
        self.align_popup.setVisible(True)

    def _apply_alignment(self, cmd):
        self._dispatch_cmd(cmd)
        self._hide_align_popup()
        ctrl = self._get_ctrl()
        if ctrl:
            self._update_button_states(ctrl)

    def _hide_align_popup(self, dispose=False):
        if hasattr(self, "align_popup") and self.align_popup:
            try:
                self.align_popup.setVisible(False)
                if dispose:
                    self.align_popup.dispose()
            except:
                pass
            if dispose:
                self.align_popup = None

    def _ensure_align_popup(self):
        if hasattr(self, "align_popup") and self.align_popup:
            return
        lg = self._is_large()
        BS = L_BTN if lg else N_BTN
        FH = L_FONT if lg else N_FONT
        
        # 4 buttons horizontally
        pw = 4 + 4 * BS + 3
        ph = BS + 4

        smgr = self.ctx.ServiceManager
        m = smgr.createInstanceWithContext(
            "com.sun.star.awt.UnoControlDialogModel", self.ctx)
        m.Width = pw
        m.Height = ph
        m.BackgroundColor = 0x2B2B2B
        m.Title = "AlignPick"
        try:
            m.Closeable = False
            m.Moveable = False
            m.Sizeable = False
        except:
            pass

        popup = smgr.createInstanceWithContext(
            "com.sun.star.awt.UnoControlDialog", self.ctx)
        popup.setModel(m)

        # Semiotics: Proposta A alignments
        align_btns = [
            ("Lft", "|\u2261",  ".uno:LeftPara",   "Alinhar à esquerda"),
            ("Ctr", " \u2261 ",  ".uno:CenterPara", "Centralizar"),
            ("Rgt", "\u2261|",  ".uno:RightPara",  "Alinhar à direita"),
            ("Jst", "|\u2261|", ".uno:JustifyPara", "Justificar")
        ]

        for i, (name, label, cmd, tooltip) in enumerate(align_btns):
            b = m.createInstance("com.sun.star.awt.UnoControlButtonModel")
            b.Name = name
            b.Label = label
            b.PositionX = 2 + i * (BS + 1)
            b.PositionY = 2
            b.Width = BS
            b.Height = BS
            b.FontHeight = FH
            b.BackgroundColor = 0x3C3C3C
            b.TextColor = 0xFFFFFF
            try:
                b.HelpText = tooltip
            except:
                pass
            m.insertByName(name, b)

        tk = smgr.createInstanceWithContext("com.sun.star.awt.Toolkit", self.ctx)
        popup.createPeer(tk, None)

        for name, label, cmd, tooltip in align_btns:
            c = popup.getControl(name)
            al = AL(lambda e, cmd=cmd: self._apply_alignment(cmd))
            self._lsnr.append(al)
            c.addActionListener(al)

        self.align_popup = popup
        fx, fy = self._get_scale_factors()
        scr_pw = int(pw * fx)
        scr_ph = int(ph * fy)
        self._remove_chrome("AlignPick", scr_pw, scr_ph)

    # ── Font change ─────────────────────────────────────────────────
    def _on_font_changed(self):
        try:
            self._busy = True
            fn = self.dialog.getControl("FontCombo").getText().strip()
            if not fn:
                return
            ctrl = self._get_ctrl()
            if not ctrl:
                return
            sel = ctrl.getSelection()
            if sel and hasattr(sel, "getCount"):
                for i in range(sel.getCount()):
                    try:
                        sel.getByIndex(i).CharFontName = fn
                    except:
                        pass
        except:
            log(f"Font err: {traceback.format_exc()}")
        finally:
            self._busy = False

    # ── Font Size change ────────────────────────────────────────────
    def _on_size_changed(self):
        try:
            self._busy = True
            sz_str = self.dialog.getControl("SizeCombo").getText().strip()
            if not sz_str:
                return
            sz_str = sz_str.replace(",", ".")
            try:
                sz = float(sz_str)
            except ValueError:
                return
            if sz <= 0:
                return
            ctrl = self._get_ctrl()
            if not ctrl:
                return
            sel = ctrl.getSelection()
            if sel and hasattr(sel, "getCount"):
                for i in range(sel.getCount()):
                    try:
                        sel.getByIndex(i).CharHeight = sz
                    except:
                        pass
        except:
            log(f"Size err: {traceback.format_exc()}")
        finally:
            self._busy = False

    def _update_size_combo(self, ctrl):
        if not self.dialog:
            return
        try:
            vc = ctrl.getViewCursor()
            sz = getattr(vc, "CharHeight", 0.0)
            if sz > 0:
                cb = self.dialog.getControl("SizeCombo")
                if cb:
                    sz_str = str(int(sz)) if sz.is_integer() else f"{sz:.1f}"
                    cb.setText(sz_str)
        except:
            pass

    # ── Color popup ─────────────────────────────────────────────────
    def _show_color_popup(self, mode):
        self._hide_align_popup()
        self.color_mode = mode
        self._ensure_color_popup()
        
        lg = self._is_large()
        sw = 9 if not lg else 12
        cols = CPOP_COLS
        rows = len(COLOR_PALETTE) // cols
        pw = 3 + cols * (sw + 1)
        ph = 3 + rows * (sw + 1)

        # Position below toolbar, centered dynamically under the respective button
        tb = self.dialog.getPosSize()
        fx, fy = self._get_scale_factors()
        scr_pw = int(pw * fx)
        scr_ph = int(ph * fy)
        
        btn_name = "Fcol" if mode == "font" else "Hlit"
        btn = self.dialog.getControl(btn_name)
        if btn:
            btn_pos = btn.getPosSize()
            pop_x = tb.X + btn_pos.X - (scr_pw - btn_pos.Width) // 2
        else:
            pop_x = tb.X
            
        pop_y = tb.Y + tb.Height + 2
        
        pos = self._clamp(Point(pop_x, pop_y), self.last_frame,
                          scr_pw, scr_ph)
        pop_x, pop_y = pos.X, pos.Y
            
        self.color_popup.setPosSize(pop_x, pop_y, scr_pw, scr_ph, 15)
        self.color_popup.setVisible(True)

    def _apply_color(self, color):
        try:
            self._busy = True
            ctrl = self._get_ctrl()
            if not ctrl:
                return
            sel = ctrl.getSelection()
            if not sel or not hasattr(sel, "getCount"):
                return
            prop = "CharColor" if self.color_mode == "font" else "CharBackColor"
            for i in range(sel.getCount()):
                try:
                    sel.getByIndex(i).setPropertyValue(prop, color)
                except:
                    pass
        except:
            log(f"Color err: {traceback.format_exc()}")
        finally:
            self._busy = False
            self._hide_color_popup()

    def _hide_color_popup(self, dispose=False):
        if hasattr(self, "color_popup") and self.color_popup:
            try:
                self.color_popup.setVisible(False)
                if dispose:
                    self.color_popup.dispose()
            except:
                pass
            if dispose:
                self.color_popup = None

    def _ensure_color_popup(self):
        if hasattr(self, "color_popup") and self.color_popup:
            return
        lg = self._is_large()
        sw = 9 if not lg else 12
        cols = CPOP_COLS
        rows = len(COLOR_PALETTE) // cols
        pw = 3 + cols * (sw + 1)
        ph = 3 + rows * (sw + 1)

        smgr = self.ctx.ServiceManager
        m = smgr.createInstanceWithContext(
            "com.sun.star.awt.UnoControlDialogModel", self.ctx)
        m.Width = pw
        m.Height = ph
        m.BackgroundColor = 0x2B2B2B
        m.Title = "ColorPick"
        try:
            m.Closeable = False
            m.Moveable = False
            m.Sizeable = False
        except:
            pass

        popup = smgr.createInstanceWithContext(
            "com.sun.star.awt.UnoControlDialog", self.ctx)
        popup.setModel(m)

        for i, color in enumerate(COLOR_PALETTE):
            row, col = divmod(i, cols)
            nm = f"c{i}"
            b = m.createInstance("com.sun.star.awt.UnoControlButtonModel")
            b.Name = nm
            b.Label = ""
            b.PositionX = 2 + col * (sw + 1)
            b.PositionY = 2 + row * (sw + 1)
            b.Width = sw
            b.Height = sw
            b.BackgroundColor = color
            m.insertByName(nm, b)

        tk = smgr.createInstanceWithContext("com.sun.star.awt.Toolkit", self.ctx)
        popup.createPeer(tk, None)

        for i, color in enumerate(COLOR_PALETTE):
            c = popup.getControl(f"c{i}")
            al = AL(lambda e, clr=color: self._apply_color(clr))
            self._lsnr.append(al)
            c.addActionListener(al)

        self.color_popup = popup
        fx, fy = self._get_scale_factors()
        scr_pw = int(pw * fx)
        scr_ph = int(ph * fy)
        self._remove_chrome("ColorPick", scr_pw, scr_ph)

    # ── Remove chrome (Win32) ───────────────────────────────────────
    def _remove_chrome(self, title, w, h):
        if not sys.platform.startswith("win"):
            return
        try:
            import ctypes
            from ctypes import wintypes
            u32 = ctypes.windll.user32
            pid = os.getpid()
            found = []
            CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

            def ep(hwnd, lp):
                ln = u32.GetWindowTextLengthW(hwnd)
                if ln <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(ln + 1)
                u32.GetWindowTextW(hwnd, buf, ln + 1)
                if buf.value != title:
                    return True
                p = wintypes.DWORD()
                u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
                if int(p.value) == pid:
                    found.append(hwnd)
                return True

            u32.EnumWindows(CB(ep), 0)
            RM = 0x00C00000 | 0x00080000 | 0x00040000 | 0x00020000 | 0x00010000
            FL = 0x0002 | 0x0004 | 0x0020
            for hwnd in found:
                st = u32.GetWindowLongW(hwnd, -16)
                ns = st & ~RM
                if ns != st:
                    u32.SetWindowLongW(hwnd, -16, ns)
                    u32.SetWindowPos(hwnd, 0, 0, 0, w, h, FL)
        except:
            pass

    # ── Command dispatch ────────────────────────────────────────────
    def _dispatch_cmd(self, cmd):
        try:
            self._busy = True
            disp = self.ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.frame.DispatchHelper", self.ctx)
            frame = self.last_frame
            if not frame:
                d = self.ctx.ServiceManager.createInstanceWithContext(
                    "com.sun.star.frame.Desktop", self.ctx)
                frame = d.getCurrentComponent().CurrentController.Frame
            disp.executeDispatch(frame, cmd, "", 0, ())
        except:
            log(f"Cmd err {cmd}: {traceback.format_exc()}")
        finally:
            self._busy = False

    def _hide(self):
        if self.dialog:
            self.dialog.setVisible(False)
        self._hide_color_popup()
        self._hide_align_popup()

    # ── XServiceInfo ────────────────────────────────────────────────
    def getImplementationName(self):
        return IMPLEMENTATION_NAME

    def supportsService(self, name):
        return name in SERVICE_NAMES

    def getSupportedServiceNames(self):
        return SERVICE_NAMES

    def disposing(self, event):
        pass


def createInstance(ctx):
    global _ACTIVE_INSTANCE
    if _ACTIVE_INSTANCE is None:
        _ACTIVE_INSTANCE = MiniToolbarExtension(ctx)
    else:
        _ACTIVE_INSTANCE.ctx = ctx
    return _ACTIVE_INSTANCE


g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(
    createInstance, IMPLEMENTATION_NAME, SERVICE_NAMES)
