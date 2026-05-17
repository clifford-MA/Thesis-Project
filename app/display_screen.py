import tkinter as tk
from datetime import datetime
import requests
import threading

from config import API_BASE_URL, REQUEST_TIMEOUT
import call_state

ADMITTING_ALWAYS    = ["Regular", "Priority"]
ADMITTING_ROTATING  = ["Special Lane", "ABTC"]

#  MONITOR DETECTION

def _get_all_monitors():
    monitors = []
    try:
        import ctypes
        import ctypes.wintypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize",    ctypes.c_ulong),
                ("rcMonitor", ctypes.wintypes.RECT),
                ("rcWork",    ctypes.wintypes.RECT),
                ("dwFlags",   ctypes.c_ulong),
            ]

        MonitorEnumProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.POINTER(ctypes.wintypes.RECT), ctypes.c_double,
        )

        def _cb(hmon, hdc, lprect, data):
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
            r = mi.rcMonitor
            w = r.right  - r.left
            h = r.bottom - r.top
            monitors.append((r.left, r.top, w, h))
            print(f"[MONITOR] Detected: {w}x{h} @ ({r.left},{r.top})")
            return True

        ctypes.windll.user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_cb), 0)

    except Exception as ex:
        print(f"[MONITOR] ctypes enum error: {ex}")

    if not monitors:
        try:
            import tkinter as _tk
            _tmp = _tk.Tk()
            _tmp.withdraw()
            sw = _tmp.winfo_screenwidth()
            sh = _tmp.winfo_screenheight()
            _tmp.destroy()
            monitors = [(0, 0, sw, sh)]
            print(f"[MONITOR] Fallback single monitor: {sw}x{sh}")
        except Exception:
            monitors = [(0, 0, 1920, 1080)]

    return monitors


def _get_monitor_for_window(win):
    win.update_idletasks()
    monitors = _get_all_monitors()
    wx, wy = win.winfo_x(), win.winfo_y()
    for (mx, my, mw, mh) in monitors:
        if mx <= wx < mx + mw and my <= wy < my + mh:
            return mx, my, mw, mh
    return monitors[0]


def _get_secondary_monitor():
    monitors = _get_all_monitors()
    print(f"[MONITOR] Total monitors detected: {len(monitors)}")
    if len(monitors) < 2:
        return None
    for m in monitors:
        if m[0] != 0 or m[1] != 0:
            return m
    return monitors[1]

#  OPEN DISPLAY SCREEN WINDOW

def open_display_screen_window(parent_dash):
    win = tk.Toplevel(parent_dash)
    win.configure(bg="#F4F6F8")

    _fs_state    = {"fullscreen": False, "prev_geo": None}
    _rebuild_job = {"id": None}
    _last_size   = {"w": 0, "h": 0}

    content_host = tk.Frame(win, bg="#F4F6F8")
    content_host.pack(fill="both", expand=True)

    def _do_fullscreen(mx, my, mw, mh):
        win.overrideredirect(True)
        win.geometry(f"{mw}x{mh}+{mx}+{my}")
        win.update()
        win.lift()
        win.focus_force()
        win.update()
        _fs_state["fullscreen"] = True
        print(f"[DISPLAY] Fullscreen → {mw}x{mh}+{mx}+{my}")

    def _enter_fullscreen():
        win.update_idletasks()
        _fs_state["prev_geo"] = win.geometry()
        mx, my, mw, mh = _get_monitor_for_window(win)
        _do_fullscreen(mx, my, mw, mh)

    def _exit_fullscreen():
        win.overrideredirect(False)
        geo = _fs_state["prev_geo"]
        if geo:
            win.geometry(geo)
        win.update()
        _fs_state["fullscreen"] = False
        win.title("ISMC OPD Queue – Display Screen  |  Drag to TV → press F for Fullscreen")
        win.lift()

    def _toggle_fullscreen(event=None):
        if _fs_state["fullscreen"]:
            _exit_fullscreen()
        else:
            _enter_fullscreen()

    win.bind("<f>",      _toggle_fullscreen)
    win.bind("<F>",      _toggle_fullscreen)
    win.bind("<Escape>", lambda e: _exit_fullscreen() if _fs_state["fullscreen"] else None)

    def _on_configure(event):
        if event.widget is not win:
            return
        nw, nh = win.winfo_width(), win.winfo_height()
        if nw == _last_size["w"] and nh == _last_size["h"]:
            return
        _last_size.update(w=nw, h=nh)
        if _rebuild_job["id"]:
            try:
                win.after_cancel(_rebuild_job["id"])
            except Exception:
                pass
        _rebuild_job["id"] = win.after(600, _rebuild_display)

    def _rebuild_display():
        try:
            for child in content_host.winfo_children():
                try:
                    child.destroy()
                except Exception:
                    pass
            win.update()
            content_host.update()
            content_host.update_idletasks()
            _build_display_content(content_host)
        except Exception as ex:
            print(f"[DISPLAY SCREEN] rebuild error: {ex}")

    win.bind("<Configure>", _on_configure)

    def _close():
        try:
            if _fs_state["fullscreen"]:
                win.overrideredirect(False)
            win.destroy()
        except Exception:
            pass

    win.protocol("WM_DELETE_WINDOW", _close)

    second = _get_secondary_monitor()

    if second:
        sx, sy, sw_tv, sh_tv = second
        print(f"[DISPLAY SCREEN] TV/HDMI detected → {sw_tv}x{sh_tv} @ ({sx},{sy})")
        win.geometry(f"200x200+{sx + sw_tv // 2 - 100}+{sy + sh_tv // 2 - 100}")
        win.update()
        _do_fullscreen(sx, sy, sw_tv, sh_tv)
    else:
        print("[DISPLAY SCREEN] Single monitor — opening windowed.")
        sw_p = win.winfo_screenwidth()
        sh_p = win.winfo_screenheight()
        ww   = int(sw_p * 0.75)
        wh   = int(sh_p * 0.75)
        win.geometry(f"{ww}x{wh}+{(sw_p - ww) // 2}+{(sh_p - wh) // 2}")
        win.minsize(800, 500)
        win.title("ISMC OPD Queue – Display Screen  |  Drag to TV → press F for Fullscreen")

    def _initial_load():
        try:
            win.update()
            content_host.update()
            content_host.update_idletasks()
            _build_display_content(content_host)
        except Exception as ex:
            print(f"[DISPLAY SCREEN] initial load error: {ex}")

    win.after(350, _initial_load)
    win.focus_force()
    return win

#  CORE DISPLAY CONTENT

def _build_display_content(parent, refresh_interval=3000):
    for widget in parent.winfo_children():
        widget.destroy()

    parent.configure(bg="#F4F6F8")
    parent.update_idletasks()

    screen_width  = parent.winfo_width()  if parent.winfo_width()  > 1 else parent.winfo_screenwidth()
    screen_height = parent.winfo_height() if parent.winfo_height() > 1 else parent.winfo_screenheight()

    print(f"[DISPLAY CONTENT] Building at {screen_width}x{screen_height}")

    title_font_size     = max(11, int(screen_width * 0.013))
    subtitle_font_size  = max(9,  int(screen_width * 0.008))
    time_font_size      = max(11, int(screen_width * 0.011))
    announce_font_size  = max(9,  int(screen_width * 0.009))
    ann_label_font_size = max(8,  int(screen_width * 0.007))
    section_label_size  = max(9,  int(screen_width * 0.009))

    header_height       = max(80, int(screen_height * 0.13))
    content_pady_top    = 0
    content_pady_bottom = max(4, int(screen_height * 0.008))
    section_bar_h       = max(24, int(screen_height * 0.032))

    total_non_grid_h = header_height + section_bar_h + content_pady_top + content_pady_bottom
    available_height = screen_height - total_non_grid_h

    box_padx = max(4, int(screen_width  * 0.005))
    box_pady = max(3, int(screen_height * 0.004))

    total_v_spacing = 3 * (box_pady * 2) + 3 * 6
    box_height = max(70, int((available_height - total_v_spacing) / 3))

    content_padding_x = int(screen_width * 0.025)
    admitting_width   = max(160, int(screen_width * 0.17))
    divider_padx      = max(6, int(screen_width * 0.008))
    divider_width     = 3

    admitting_right_pad_calc = divider_padx * 2 + divider_width
    admitting_total_w = admitting_width + content_padding_x + admitting_right_pad_calc

    opd_outer_pad   = box_padx + (content_padding_x + box_padx)
    per_box_pad     = (box_padx * 2 + 6) * 3
    opd_available_w = screen_width - admitting_total_w - opd_outer_pad - per_box_pad
    box_width = max(80, int(opd_available_w / 3))

    box_ref = min(box_height, box_width)

    service_title_size = max(8,  min(22, int(box_ref * 0.085)))
    serving_size       = max(12, min(46, int(box_ref * 0.175)))
    waiting_size       = max(11, min(38, int(box_ref * 0.140)))
    label_size         = max(7,  min(16, int(box_ref * 0.062)))
    next_ticket_size   = max(9,  min(18, int(box_ref * 0.080)))

    # Padding
    box_top_pad    = max(6,  int(box_height * 0.06))
    box_inner_pad  = max(4,  int(box_height * 0.03))

    print(f"[DISPLAY] {screen_width}x{screen_height} | box={box_width}x{box_height}")

    # LIFECYCLE
    is_active = {"value": True}
    after_ids = []

    def safe_after(delay, func):
        if is_active["value"]:
            try:
                aid = parent.after(delay, func)
                after_ids.append(aid)
                return aid
            except tk.TclError:
                is_active["value"] = False
        return None

    def cleanup(e=None):
        if e and e.widget is not parent:
            return
        is_active["value"] = False
        for aid in after_ids:
            try:
                parent.after_cancel(aid)
            except Exception:
                pass
        after_ids.clear()

    parent.bind("<Destroy>", cleanup)

    # HEADER
    header = tk.Frame(parent, bg="#1A237E", height=header_height)
    header.pack(fill="x")
    header.pack_propagate(False)

    header_content = tk.Frame(header, bg="#1A237E")
    header_content.place(relx=0, rely=0, relwidth=1, relheight=1)

    try:
        import tkinter.font as _fmod
        _time_f = _fmod.Font(family="Segoe UI", size=time_font_size, weight="bold")
        _date_f = _fmod.Font(family="Segoe UI", size=subtitle_font_size)
        _right_col_w = max(
            _time_f.measure("00:00:00 PM"),
            _date_f.measure("Wednesday, December 00, 0000")
        ) + max(10, int(screen_width * 0.008))
    except Exception:
        _right_col_w = max(180, int(screen_width * 0.15))

    _right_margin = int(screen_width * 0.025)

    left_hdr = tk.Frame(header_content, bg="#1A237E")
    left_hdr.place(relx=0, rely=0.5, anchor="w", x=int(screen_width * 0.025))

    tk.Label(left_hdr, text="ILOCOS SUR MEDICAL CENTER",
             font=("Segoe UI", title_font_size, "bold"),
             bg="#1A237E", fg="white").pack(anchor="w")

    right_hdr = tk.Frame(header_content, bg="#1A237E")
    right_hdr.place(relx=1.0, rely=0.5, anchor="e",
                    x=-_right_margin, width=_right_col_w)

    time_label = tk.Label(right_hdr, font=("Segoe UI", time_font_size, "bold"),
                          bg="#1A237E", fg="#FFFFFF")
    time_label.pack(anchor="e")

    date_label = tk.Label(right_hdr, font=("Segoe UI", subtitle_font_size),
                          bg="#1A237E", fg="#C5CAE9")
    date_label.pack(anchor="e", pady=(int(header_height * 0.03), 0))

    def update_time():
        if not is_active["value"]:
            return
        try:
            if time_label.winfo_exists() and date_label.winfo_exists():
                now = datetime.now()
                time_label.config(text=now.strftime("%I:%M:%S %p"))
                date_label.config(text=now.strftime("%A, %B %d, %Y"))
                safe_after(1000, update_time)
        except tk.TclError:
            is_active["value"] = False

    update_time()

    # ANNOUNCEMENT
    try:
        import tkinter.font as tkfont
        _tf = tkfont.Font(family="Segoe UI", size=title_font_size, weight="bold")
        _measured_title_w = _tf.measure("ILOCOS SUR MEDICAL CENTER")
    except Exception:
        _measured_title_w = max(240, int(screen_width * 0.26))

    _title_margin = int(screen_width * 0.025)
    _title_gap    = max(16, int(screen_width * 0.015))
    _ann_x1       = _title_margin + _measured_title_w + _title_gap
    _right_gap    = max(16, int(screen_width * 0.015))
    _ann_x2       = screen_width - _right_margin - _right_col_w - _right_gap

    ann_center_w  = max(200, _ann_x2 - _ann_x1)
    ann_center_h  = max(44, int(header_height * 0.72))
    ann_center_x  = (_ann_x1 + _ann_x2) // 2

    ann_outer = tk.Frame(header_content, bg="#283593",
                         width=ann_center_w, height=ann_center_h)
    ann_outer.place(x=ann_center_x, rely=0.5, anchor="center")
    ann_outer.pack_propagate(False)

    ann_lbl_h = max(18, int(ann_center_h * 0.36))
    ann_lbl_bar = tk.Frame(ann_outer, bg="#283593", height=ann_lbl_h)
    ann_lbl_bar.pack(fill="x")
    ann_lbl_bar.pack_propagate(False)
    tk.Label(ann_lbl_bar, text="\U0001f4e2 ANNOUNCEMENTS",
             font=("Segoe UI", ann_label_font_size, "bold"),
             bg="#283593", fg="white", padx=8).pack(side="left", anchor="center")

    ann_body = tk.Frame(ann_outer, bg="white")
    ann_body.pack(fill="both", expand=True, padx=2, pady=(0, 2))

    ann_canvas_h = max(20, ann_center_h - ann_lbl_h - 4)
    ann_canvas = tk.Canvas(ann_body, bg="white", height=ann_canvas_h,
                           highlightthickness=0, bd=0)
    ann_canvas.pack(fill="both", expand=True)

    scroll_x      = [ann_center_w]
    announce_text = [""]
    text_id       = [None]

    def _fetch_announcement():
        try:
            r = requests.get(f"{API_BASE_URL}/announcements/current", timeout=1)
            if r.status_code == 200:
                d = r.json()
                if d.get("success") and d.get("message"):
                    try:
                        parent.after(0, lambda m=d["message"]: _apply_announcement(m))
                    except Exception:
                        pass
                    return
        except Exception as e:
            print(f"[DISPLAY] announcement error: {e}")
        default = ("\U0001f3e5 Welcome to ISMC Outpatient Department  \u2022  "
                   "Please wait for your ticket number to be called  \u2022  "
                   "Thank you for your patience")
        try:
            parent.after(0, lambda m=default: _apply_announcement(m))
        except Exception:
            pass

    def _apply_announcement(txt):
        if txt != announce_text[0]:
            announce_text[0] = txt
            scroll_x[0] = ann_canvas.winfo_width() or ann_center_w

    def refresh_announcement():
        if not is_active["value"]:
            return
        threading.Thread(target=_fetch_announcement, daemon=True).start()
        safe_after(30_000, refresh_announcement)

    def animate_scroll():
        if not is_active["value"]:
            return
        try:
            if not ann_canvas.winfo_exists():
                return
            cw = ann_canvas.winfo_width() or ann_center_w
            ch = ann_canvas.winfo_height() or ann_canvas_h
            if text_id[0]:
                ann_canvas.delete(text_id[0])
            text_id[0] = ann_canvas.create_text(
                scroll_x[0], ch // 2,
                text=announce_text[0],
                font=("Segoe UI", announce_font_size, "bold"),
                fill="#1A237E", anchor="w")
            bbox = ann_canvas.bbox(text_id[0])
            tw = (bbox[2] - bbox[0]) if bbox else 0
            scroll_x[0] -= 2.5
            if scroll_x[0] + tw < 0:
                scroll_x[0] = cw
            safe_after(30, animate_scroll)
        except tk.TclError:
            is_active["value"] = False

    announce_text[0] = ("\U0001f3e5 Welcome to ISMC Outpatient Department  \u2022  "
                        "Please wait for your ticket number to be called  \u2022  "
                        "Thank you for your patience")
    threading.Thread(target=_fetch_announcement, daemon=True).start()
    refresh_announcement()
    animate_scroll()

    # SECTION BAR
    section_bar = tk.Frame(parent, bg="#283593", height=section_bar_h)
    section_bar.pack(fill="x")
    section_bar.pack_propagate(False)

    section_inner = tk.Frame(section_bar, bg="#283593")
    section_inner.place(relx=0, rely=0, relwidth=1, relheight=1)

    admitting_col_center = content_padding_x + admitting_width // 2
    tk.Label(section_inner, text="ADMITTING",
             font=("Segoe UI", section_label_size, "bold"),
             bg="#283593", fg="white").place(x=admitting_col_center, rely=0.5, anchor="center")

    opd_start = content_padding_x + admitting_width + divider_padx * 2 + divider_width
    opd_end   = screen_width - content_padding_x
    opd_col_center = opd_start + (opd_end - opd_start) // 2
    tk.Label(section_inner, text="OUTPATIENT DEPARTMENT",
             font=("Segoe UI", section_label_size, "bold"),
             bg="#283593", fg="white").place(x=opd_col_center, rely=0.5, anchor="center")

    # MAIN CONTENT AREA
    ADMITTING_BG = "#283593"

    content_frame = tk.Frame(parent, bg="#F4F6F8")
    content_frame.pack(fill="both", expand=True, padx=0, pady=0)

    admitting_right_pad = admitting_right_pad_calc
    admitting_panel = tk.Frame(content_frame, bg=ADMITTING_BG,
                               width=admitting_width + content_padding_x + admitting_right_pad)
    admitting_panel.pack(side="left", fill="both")
    admitting_panel.pack_propagate(False)

    admitting_frame_widget = tk.Frame(admitting_panel, bg=ADMITTING_BG, width=admitting_width)
    admitting_frame_widget.place(x=content_padding_x, rely=0, anchor="nw",
                                 relheight=1, width=admitting_width)
    admitting_frame_widget.pack_propagate(False)

    opd_frame = tk.Frame(content_frame, bg="#F4F6F8")
    opd_frame.pack(side="left", fill="both", expand=True,
                   padx=(box_padx, content_padding_x + box_padx))

    # ADMITTING COLORS & STATE
    admitting_colors = {
        "Regular":      "#81C784",
        "Priority":     "#E57373",
        "Special Lane": "#64B5F6",
        "ABTC":         "#BBCB80",
    }

    admitting_labels         = {}
    admitting_waiting_labels = {}
    admitting_next_labels    = {}
    admitting_card_frames    = {}

    _admitting_data   = {}
    _slot3_shown      = {"v": "Special Lane"}

    # OPD state — no rotation, always page 0
    _all_services          = []
    _rotation_page         = {"idx": 0}
    _rotation_job          = {"id": None}
    current_displayed_page = {"idx": -1}
    current_displayed_ids  = []
    SERVICES_PER_PAGE = 9

    # ADMITTING HELPERS

    def _has_activity_a(queue_type):
        info    = _admitting_data.get(queue_type, {})
        current = info.get("current")
        waiting = int(info.get("waiting", 0))
        return bool(current) or waiting > 0

    next_h           = max(28, int(box_height * 0.20))
    next_pady_bottom = max(6,  int(box_height * 0.04))

    # ADMITTING BOX LAYOUT

    def create_admitting_box(queue_type, color):
        card = tk.Frame(admitting_frame_widget, bg=color, height=box_height + 6)
        card.pack(fill="x", pady=(box_pady, box_pady))
        card.pack_propagate(False)

        card_inner = tk.Frame(card, bg=color)
        card_inner.place(x=0, y=0, relwidth=1, relheight=1)

        # TOP: Queue type label
        title_lbl = tk.Label(card_inner, text=queue_type,
                             font=("Segoe UI", service_title_size, "bold"),
                             bg=color, fg="black", anchor="center")
        title_lbl.place(relx=0.5, rely=0, anchor="n",
                        y=box_top_pad, relwidth=1)

        # BOTTOM: Next
        next_canvas = tk.Canvas(card_inner, bg=color, height=next_h,
                                highlightthickness=0, bd=0)
        next_canvas.place(relx=0.5, rely=1.0, anchor="s",
                          y=-next_pady_bottom, relwidth=0.92)
        next_canvas._bg = color

        # MIDDLE: ticket
        mid_frame = tk.Frame(card_inner, bg=color)
        mid_frame.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.92)

        # Row 1
        row1 = tk.Frame(mid_frame, bg=color)
        row1.pack(fill="x")

        ticket_lbl = tk.Label(row1, text="---",
                              font=("Segoe UI", serving_size, "bold"),
                              bg=color, fg="black", anchor="w")
        ticket_lbl.pack(side="left")

        waiting_lbl = tk.Label(row1, text="0",
                               font=("Segoe UI", waiting_size, "bold"),
                               bg=color, fg="black", anchor="e")
        waiting_lbl.pack(side="right")

        # Row 2
        row2 = tk.Frame(mid_frame, bg=color)
        row2.pack(fill="x", pady=(max(1, int(box_height * 0.01)), 0))

        tk.Label(row2, text="Currently Serving",
                 font=("Segoe UI", label_size),
                 bg=color, fg="black", anchor="w").pack(side="left")
        tk.Label(row2, text="Waiting",
                 font=("Segoe UI", label_size),
                 bg=color, fg="black", anchor="e").pack(side="right")

        admitting_labels[queue_type]         = ticket_lbl
        admitting_waiting_labels[queue_type] = waiting_lbl
        admitting_next_labels[queue_type]    = next_canvas
        admitting_card_frames[queue_type]    = card

    for qt in ADMITTING_ALWAYS:
        create_admitting_box(qt, admitting_colors[qt])
    for qt in ADMITTING_ROTATING:
        create_admitting_box(qt, admitting_colors[qt])

    admitting_card_frames["ABTC"].pack_forget()

    # ADMITTING SLOT

    def _show_slot3(queue_type):
        if _slot3_shown["v"] == queue_type:
            return
        other = "ABTC" if queue_type == "Special Lane" else "Special Lane"
        try:
            admitting_card_frames[other].pack_forget()
            admitting_card_frames[queue_type].pack(fill="x", pady=(box_pady, box_pady))
        except Exception as e:
            print(f"[DISPLAY] slot3 show error: {e}")
            return
        _slot3_shown["v"] = queue_type
        print(f"[DISPLAY] Admitting slot 3 → {queue_type}")

    def _update_slot3_from_data(server_call_state=None):
        sl_active   = _has_activity_a("Special Lane")
        abtc_active = _has_activity_a("ABTC")

        # Only honour server_call_state if that queue STILL has activity.
        # If the ticket was already served (no activity), treat call_state as stale
        # and fall through to the activity-based logic below.
        if server_call_state == "Special Lane" and sl_active:
            _show_slot3("Special Lane")
            return
        if server_call_state == "ABTC" and abtc_active:
            _show_slot3("ABTC")
            return

        # call_state is absent or stale — decide purely from live ticket data
        if abtc_active and not sl_active:
            # Only ABTC has tickets → show ABTC
            _show_slot3("ABTC")
        elif sl_active and not abtc_active:
            # Only SL has tickets → show SL
            _show_slot3("Special Lane")
        elif abtc_active and sl_active:
            # Both have tickets → keep whatever is currently shown, no forced switch
            pass
        else:
            # Neither has tickets → default back to Special Lane
            _show_slot3("Special Lane")

    # NEXT-TICKET

    def _short_tickets(next_list):
        short = []
        for t in (next_list or [])[:3]:
            parts = str(t).split("-", 1)
            short.append(parts[1] if len(parts) == 2 else str(t))
        return short

    def _draw_next_canvas(canvas, tickets, bg_color="white", fg_color="#1A237E",
                          lbl_color="#546E7A", has_more=False, lbl_bold=True):
        try:
            canvas.update_idletasks()
            w = canvas.winfo_width()
            h = canvas.winfo_height()
            if w < 2: w = canvas.winfo_reqwidth()
            if h < 2: h = canvas.winfo_reqheight()
            canvas.delete("all")
            mid_y = max(1, h // 2)

            import tkinter.font as tkfont

            def measure(text, size):
                try:
                    return tkfont.Font(family="Segoe UI", size=size, weight="bold").measure(text)
                except Exception:
                    return size * len(text)

            MIN_GAP  = 10
            fit_size = next_ticket_size
            for try_size in range(next_ticket_size, 5, -1):
                parts = ["Next:"] + list(tickets)
                if has_more:
                    parts.append("▶")
                total = sum(measure(p, try_size) for p in parts) + MIN_GAP * (len(parts) - 1)
                if total <= w - 4:
                    fit_size = try_size
                    break

            lbl_weight = "bold" if lbl_bold else "normal"
            lbl_font  = ("Segoe UI", fit_size, lbl_weight)
            tick_font = ("Segoe UI", fit_size, "bold")
            lbl_w   = measure("Next:", fit_size)
            arrow_w = measure("▶", fit_size) if has_more else 0

            canvas.create_text(2, mid_y, text="Next:", font=lbl_font,
                                fill=lbl_color, anchor="w")
            if has_more:
                canvas.create_text(w - 2, mid_y, text="▶", font=tick_font,
                                   fill=fg_color, anchor="e")
            if tickets:
                x_start = 2 + lbl_w + MIN_GAP
                x_end   = (w - 2 - arrow_w - MIN_GAP) if has_more else (w - 2)
                slot    = (x_end - x_start) / len(tickets)
                for i, t in enumerate(tickets):
                    cx = x_start + slot * i + slot / 2
                    canvas.create_text(int(cx), mid_y, text=t, font=tick_font,
                                       fill=fg_color, anchor="center")
        except Exception:
            pass

    def _update_next_canvas(canvas, next_list, bg_color="white",
                            fg_color="#1A237E", lbl_color="#2E7D32", lbl_bold=True):
        tickets  = _short_tickets(next_list)
        has_more = len(next_list) > 3 if next_list else False
        _draw_next_canvas(canvas, tickets, bg_color, fg_color, lbl_color, has_more, lbl_bold)

    # OPD GRID
    service_widgets = {}

    def _service_is_active(svc):
        has_waiting = int(svc.get("waiting", 0)) > 0
        serving_val = svc.get("serving")
        has_serving = bool(serving_val) and str(serving_val).strip() not in ("", "---")
        return has_waiting or has_serving

    def _get_page_services():
        # Always show only the first SERVICES_PER_PAGE (9) services — no rotation.
        if not _all_services:
            return []
        return _all_services[:SERVICES_PER_PAGE]

    def _cancel_rotation():
        if _rotation_job["id"]:
            try:
                parent.after_cancel(_rotation_job["id"])
            except Exception:
                pass
            _rotation_job["id"] = None

    def rebuild_grid(services_to_display):
        if not is_active["value"]:
            return
        try:
            for w in opd_frame.winfo_children():
                try:
                    w.destroy()
                except Exception:
                    pass
            service_widgets.clear()

            capped = services_to_display[:SERVICES_PER_PAGE]
            if not capped:
                ef = tk.Frame(opd_frame, bg="#F4F6F8")
                ef.place(relx=0.5, rely=0.5, anchor="center")
                tk.Label(ef, text="\u2695\ufe0f", font=("Segoe UI", 48),
                         bg="#F4F6F8", fg="#9E9E9E").pack(pady=(0, 10))
                tk.Label(ef, text="No OPD Services Available",
                         font=("Segoe UI", 18, "bold"),
                         bg="#F4F6F8", fg="#E53935").pack(pady=(0, 5))
                tk.Label(ef, text="Please add services in OPD Services Management",
                         font=("Segoe UI", 12), bg="#F4F6F8", fg="#757575").pack()
                return

            current_row_frame = None
            for idx, svc in enumerate(capped):
                if not is_active["value"]:
                    break
                if idx % 3 == 0:
                    current_row_frame = tk.Frame(opd_frame, bg="#F4F6F8")
                    current_row_frame.pack(side="top", fill="x", pady=(box_pady, box_pady))

                sid   = svc["service_id"]
                name  = svc["service_name"]
                color = svc.get("color", "#1E88E5")

                border_thickness = max(3, int(box_ref * 0.028))

                shadow = tk.Frame(current_row_frame, bg="#B0BEC5",
                                  width=box_width + 6, height=box_height + 6)
                shadow.pack(side="left", padx=(box_padx, box_padx))
                shadow.pack_propagate(False)

                card = tk.Frame(shadow, bg=color, width=box_width, height=box_height)
                card.place(x=3, y=3)
                card.pack_propagate(False)

                # White inner card
                inner_card = tk.Frame(card, bg="white")
                inner_card.place(x=border_thickness, y=border_thickness,
                                 width=box_width  - border_thickness * 2,
                                 height=box_height - border_thickness * 2)
                inner_card.pack_propagate(False)

                inner_w = box_width  - border_thickness * 2
                inner_h = box_height - border_thickness * 2
                px = max(6, int(inner_w * 0.05))

                # TOP: Service name label
                title_lbl = tk.Label(inner_card, text=name,
                                     font=("Segoe UI", service_title_size, "bold"),
                                     bg="white", fg="#1A237E",
                                     wraplength=inner_w - px * 2,
                                     anchor="center", justify="center")
                title_lbl.place(relx=0.5, rely=0, anchor="n",
                                y=box_top_pad, width=inner_w - px * 2)

                # BOTTOM: Next
                opd_next_h = max(22, int(inner_h * 0.18))
                next_canvas = tk.Canvas(inner_card, bg="white", height=opd_next_h,
                                        highlightthickness=0, bd=0)
                next_canvas.place(relx=0.5, rely=1.0, anchor="s",
                                  y=-next_pady_bottom,
                                  width=inner_w - px * 2)

                # MIDDLE: ticket + waiting
                mid_frame = tk.Frame(inner_card, bg="white")
                mid_frame.place(relx=0.5, rely=0.5, anchor="center",
                                width=inner_w - px * 2)

                row1 = tk.Frame(mid_frame, bg="white")
                row1.pack(fill="x")

                serving_lbl = tk.Label(row1, text="---",
                                       font=("Segoe UI", serving_size, "bold"),
                                       bg="white", fg="#1A237E", anchor="w")
                serving_lbl.pack(side="left")

                waiting_lbl = tk.Label(row1, text="0",
                                       font=("Segoe UI", waiting_size, "bold"),
                                       bg="white", fg="#E53935", anchor="e")
                waiting_lbl.pack(side="right")

                row2 = tk.Frame(mid_frame, bg="white")
                row2.pack(fill="x", pady=(max(1, int(inner_h * 0.01)), 0))

                tk.Label(row2, text="Currently Serving",
                         font=("Segoe UI", label_size),
                         bg="white", fg="#546E7A", anchor="w").pack(side="left")
                tk.Label(row2, text="Waiting",
                         font=("Segoe UI", label_size),
                         bg="white", fg="#546E7A", anchor="e").pack(side="right")

                service_widgets[sid] = {
                    "serving_label": serving_lbl,
                    "waiting_label": waiting_lbl,
                    "next_canvas":   next_canvas,
                }

        except Exception as e:
            print(f"[DISPLAY] rebuild_grid error: {e}")

    def _show_page():
        # Always show only the first 9 services — no rotation ever.
        page    = _get_page_services()
        new_ids = [s["service_id"] for s in page]

        if new_ids != current_displayed_ids:
            rebuild_grid(page)
            current_displayed_page["idx"] = 0
            current_displayed_ids.clear()
            current_displayed_ids.extend(new_ids)

        _update_service_widgets(page)

    # DATA FETCH

    def _fetch_all_data():
        if not is_active["value"]:
            return

        admitting_result  = {}
        services_result   = []
        server_call_state = None

        try:
            r = requests.get(f"{API_BASE_URL}/display/admitting", timeout=2)
            if r.status_code == 200:
                d = r.json()
                if d.get("success"):
                    admitting_result = d.get("admitting", {})
        except Exception as e:
            print(f"[DISPLAY] admitting fetch error: {e}")

        try:
            r = requests.get(f"{API_BASE_URL}/display/services", timeout=2)
            if r.status_code == 200:
                d = r.json()
                if d.get("success"):
                    services_result = d.get("services", [])
        except Exception as e:
            print(f"[DISPLAY] services fetch error: {e}")

        try:
            r = requests.get(f"{API_BASE_URL}/call-state", timeout=1)
            if r.status_code == 200:
                d = r.json()
                if d.get("success"):
                    server_call_state = d.get("queue_type")
        except Exception as e:
            print(f"[DISPLAY] call-state fetch error: {e}")

        try:
            parent.after(0, lambda: _apply_data(
                admitting_result, services_result, server_call_state))
        except Exception:
            pass

    def _update_service_widgets(services_on_screen):
        for svc in services_on_screen:
            sid = svc["service_id"]
            if sid not in service_widgets:
                continue
            try:
                if not service_widgets[sid]["serving_label"].winfo_exists():
                    continue
            except Exception:
                continue
            try:
                service_widgets[sid]["serving_label"].config(
                    text=str(svc.get("serving") or "---"))
                service_widgets[sid]["waiting_label"].config(
                    text=str(svc.get("waiting", 0)))
                _update_next_canvas(service_widgets[sid]["next_canvas"],
                                    svc.get("next_tickets", []))
            except Exception:
                pass

    def _apply_data(admitting_data, services, server_call_state=None):
        if not is_active["value"]:
            return

        _admitting_data.clear()
        _admitting_data.update(admitting_data)

        for qt in ADMITTING_ALWAYS + ADMITTING_ROTATING:
            if qt not in admitting_labels:
                continue
            try:
                if not admitting_labels[qt].winfo_exists():
                    continue
            except Exception:
                continue
            info    = admitting_data.get(qt, {})
            current = info.get("current") or "---"
            waiting = str(info.get("waiting", 0))
            next_tickets = info.get("next_tickets", [])
            try:
                admitting_labels[qt].config(text=current)
                admitting_waiting_labels[qt].config(text=waiting)
                _update_next_canvas(admitting_next_labels[qt], next_tickets,
                                    bg_color=admitting_next_labels[qt]._bg,
                                    fg_color="black", lbl_color="black", lbl_bold=False)
            except Exception:
                pass

        _update_slot3_from_data(server_call_state)

        _all_services.clear()
        _all_services.extend(services)

        # Always show page 0 — no rotation logic needed.
        _cancel_rotation()
        _show_page()

    def schedule_next_fetch():
        def _trigger():
            if is_active["value"]:
                threading.Thread(target=_fetch_all_data, daemon=True).start()
                safe_after(refresh_interval, schedule_next_fetch)
        safe_after(refresh_interval, _trigger)

    threading.Thread(target=_fetch_all_data, daemon=True).start()
    schedule_next_fetch()

    print(f"[DISPLAY CONTENT] Loaded — {screen_width}x{screen_height} | "
          f"box={box_width}x{box_height}")