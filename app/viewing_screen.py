import tkinter as tk
from datetime import datetime
import requests
import threading

from config import API_BASE_URL, REQUEST_TIMEOUT
import call_state

# ADMITTING ROTATION CONFIG

ADMITTING_ALWAYS    = ["Regular", "Priority"]
ADMITTING_ROTATING  = ["Special Lane", "ABTC"]


def viewing_screen_frame(parent, refresh_interval=3000):
    """
    Display Screen — FULLY THREADED API VERSION
    Every API call runs in a background thread so the UI NEVER freezes.
    Works on both server and client laptops.
    """
    for widget in parent.winfo_children():
        widget.destroy()

    parent.configure(bg="#F4F6F8")
    parent.update_idletasks()

    screen_width  = parent.winfo_width()  if parent.winfo_width()  > 1 else parent.winfo_screenwidth()
    screen_height = parent.winfo_height() if parent.winfo_height() > 1 else parent.winfo_screenheight()

    header_height    = max(80,  min(130, int(screen_height * 0.13)))

    content_pady_top    = 0
    content_pady_bottom = max(4, int(screen_height * 0.008))
    section_bar_h       = max(24, int(screen_height * 0.032))

    total_non_grid_h = (
        header_height
        + section_bar_h
        + content_pady_top  + content_pady_bottom
    )
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

    opd_outer_pad  = box_padx + (content_padding_x + box_padx)
    per_box_pad    = (box_padx * 2 + 6) * 3
    opd_available_w = screen_width - admitting_total_w - opd_outer_pad - per_box_pad
    box_width = max(80, int(opd_available_w / 3))

    title_font_size    = max(11, min(22, int(screen_width  * 0.013)))
    subtitle_font_size = max(9,  min(15, int(screen_width  * 0.008)))
    time_font_size     = max(11, min(20, int(screen_width  * 0.009)))
    announce_font_size = max(9,  min(14, int(screen_width  * 0.007)))
    ann_label_font_size = max(8, min(12, int(screen_width  * 0.006)))
    section_label_size  = max(9, min(14, int(screen_width  * 0.009)))

    box_ref = min(box_height, box_width)

    service_title_size = max(8,  min(15, int(box_height * 0.10)))
    serving_size       = max(14, min(32, int(box_height * 0.22)))
    waiting_size       = max(13, min(26, int(box_height * 0.18)))
    label_size         = max(7,  min(11, int(box_height * 0.075)))
    next_label_size    = max(9,  min(18, int(box_ref * 0.080)))
    next_ticket_size   = max(9,  min(18, int(box_ref * 0.080)))

    print(f"[VIEWING SCREEN] {screen_width}x{screen_height} | box={box_width}x{box_height}")

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

    def cleanup():
        is_active["value"] = False
        for aid in after_ids:
            try:
                parent.after_cancel(aid)
            except:
                pass
        after_ids.clear()

    parent.bind("<Destroy>", lambda e: cleanup() if e.widget == parent else None)

    # HEADER
    header = tk.Frame(parent, bg="#1A237E", height=header_height)
    header.pack(fill="x")
    header.pack_propagate(False)

    header_content = tk.Frame(header, bg="#1A237E")
    header_content.place(relx=0, rely=0, relwidth=1, relheight=1)

    left_hdr = tk.Frame(header_content, bg="#1A237E")
    left_hdr.place(relx=0, rely=0.5, anchor="w",
                   x=int(screen_width * 0.025))

    tk.Label(left_hdr, text="ILOCOS SUR MEDICAL CENTER",
             font=("Segoe UI", title_font_size, "bold"),
             bg="#1A237E", fg="white").pack(anchor="w")

    right_hdr = tk.Frame(header_content, bg="#1A237E")
    right_hdr.place(relx=1.0, rely=0.5, anchor="e",
                    x=-int(screen_width * 0.025))

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

    _right_w      = max(160, int(screen_width * 0.14))
    _right_gap    = max(12,  int(screen_width * 0.012))
    _ann_x2       = screen_width - _right_w - _right_gap

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
    tk.Label(ann_lbl_bar, text="📢 ANNOUNCEMENTS",
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
                    parent.after(0, lambda: _apply_announcement(d["message"]))
                    return
        except Exception as e:
            print(f"[VIEWING] announcement error: {e}")
        default = ("🏥 Welcome to ISMC Outpatient Department  •  "
                   "Please wait for your ticket number to be called  •  "
                   "Thank you for your patience")
        try:
            parent.after(0, lambda: _apply_announcement(default))
        except:
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

    announce_text[0] = ("🏥 Welcome to ISMC Outpatient Department  •  "
                        "Please wait for your ticket number to be called  •  "
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

    # MAIN CONTENT
    ADMITTING_BG = "#283593"

    content_frame = tk.Frame(parent, bg="#F4F6F8")
    content_frame.pack(fill="both", expand=True, padx=0, pady=0)

    admitting_right_pad = admitting_right_pad_calc
    admitting_panel = tk.Frame(content_frame, bg=ADMITTING_BG,
                               width=admitting_width + content_padding_x + admitting_right_pad)
    admitting_panel.pack(side="left", fill="both")
    admitting_panel.pack_propagate(False)

    admitting_frame = tk.Frame(admitting_panel, bg=ADMITTING_BG, width=admitting_width)
    admitting_frame.place(x=content_padding_x, rely=0, anchor="nw",
                          relheight=1, width=admitting_width)
    admitting_frame.pack_propagate(False)

    opd_frame = tk.Frame(content_frame, bg="#F4F6F8")
    opd_frame.pack(side="left", fill="both", expand=True,
                   padx=(box_padx, content_padding_x + box_padx))

    # ADMITTING COLORS
    admitting_colors = {
        "Regular":      "#81C784",
        "Priority":     "#E57373",
        "Special Lane": "#64B5F6",
        "ABTC":         "#80CBC4",
    }

    admitting_labels         = {}
    admitting_waiting_labels = {}
    admitting_next_labels    = {}
    admitting_card_frames    = {}

    _admitting_data  = {}
    _slot3_shown     = {"v": "Special Lane"}

    def _has_activity(queue_type):
        info = _admitting_data.get(queue_type, {})
        current = info.get("current")
        waiting = int(info.get("waiting", 0))
        return bool(current) or waiting > 0

    def create_admitting_box(queue_type, color):
        card = tk.Frame(admitting_frame, bg=color, height=box_height + 6)
        card.pack(fill="x", pady=(box_pady, box_pady))
        card.pack_propagate(False)

        inner = tk.Frame(card, bg=color)
        inner.pack(fill="both", expand=True, padx=10, pady=4)

        next_h = max(28, int(box_height * 0.22))
        next_canvas = tk.Canvas(inner, bg=color, height=next_h,
                                highlightthickness=0, bd=0)
        next_canvas.pack(side="bottom", fill="x", padx=4,
                         pady=(max(2, int(box_height * 0.010)),
                               max(8, int(box_height * 0.050))))
        next_canvas._bg = color

        tk.Label(inner, text=queue_type,
                 font=("Segoe UI", service_title_size, "bold"),
                 bg=color, fg="black").pack(
                     pady=(max(2, int(box_height * 0.03)), max(1, int(box_height * 0.01))))

        mid = tk.Frame(inner, bg=color)
        mid.pack(fill="x", padx=4)

        ticket_lbl = tk.Label(mid, text="---",
                              font=("Segoe UI", serving_size, "bold"),
                              bg=color, fg="black")
        ticket_lbl.pack(side="left", anchor="w")

        waiting_lbl = tk.Label(mid, text="0",
                               font=("Segoe UI", waiting_size, "bold"),
                               bg=color, fg="black")
        waiting_lbl.pack(side="right", anchor="e")

        bot = tk.Frame(inner, bg=color)
        bot.pack(fill="x", padx=4,
                 pady=(max(1, int(box_height * 0.010)), max(1, int(box_height * 0.010))))

        tk.Label(bot, text="Currently Serving",
                 font=("Segoe UI", label_size),
                 bg=color, fg="black").pack(side="left", anchor="w")
        tk.Label(bot, text="Waiting",
                 font=("Segoe UI", label_size),
                 bg=color, fg="black").pack(side="right", anchor="e")

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
            print(f"[VIEWING] slot3 show error: {e}")
            return
        _slot3_shown["v"] = queue_type
        print(f"[VIEWING] Admitting slot 3 → {queue_type}")

    def _update_slot3_from_data(server_call_state=None):
        """
        Decide which rotating queue to show in slot 3.
        Priority:
          1. server_call_state passed in (fetched from API) → use it immediately
          2. Both have activity  → keep current (no flicker)
          3. Only ABTC active   → show ABTC
          4. Only SL active     → show Special Lane
          5. Neither active     → show Special Lane (default)
        """
        # Use server-fetched
        if server_call_state in ("Special Lane", "ABTC"):
            _show_slot3(server_call_state)
            return

        # Fallback
        sl_active   = _has_activity("Special Lane")
        abtc_active = _has_activity("ABTC")

        if sl_active and abtc_active:
            pass
        elif abtc_active:
            _show_slot3("ABTC")
        else:
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
            if w < 2:
                w = canvas.winfo_reqwidth()
            if h < 2:
                h = canvas.winfo_reqheight()
            canvas.delete("all")
            mid_y = max(1, h // 2)

            import tkinter.font as tkfont

            def measure(text, size):
                try:
                    return tkfont.Font(family="Segoe UI", size=size, weight="bold").measure(text)
                except Exception:
                    return size * len(text)

            MIN_GAP = 10
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
            tick_ws = [measure(t, fit_size) for t in tickets]
            arrow_w = measure("▶", fit_size) if has_more else 0

            canvas.create_text(2, mid_y, text="Next:", font=lbl_font,
                                fill=lbl_color, anchor="w")

            if has_more:
                canvas.create_text(w - 2, mid_y, text="▶", font=tick_font,
                                   fill=fg_color, anchor="e")

            if tickets:
                tickets_x_start = 2 + lbl_w + MIN_GAP
                tickets_x_end   = (w - 2 - arrow_w - MIN_GAP) if has_more else (w - 2)
                avail = tickets_x_end - tickets_x_start
                slot  = avail / len(tickets)
                for i, (t, tw) in enumerate(zip(tickets, tick_ws)):
                    cx = tickets_x_start + slot * i + slot / 2
                    canvas.create_text(int(cx), mid_y, text=t, font=tick_font,
                                       fill=fg_color, anchor="center")
        except Exception:
            pass

    def _update_next_canvas(canvas, next_list, bg_color="white",
                            fg_color="#1A237E", lbl_color="#2E7D32", lbl_bold=True):
        tickets  = _short_tickets(next_list)
        has_more = len(next_list) > 3 if next_list else False
        _draw_next_canvas(canvas, tickets, bg_color, fg_color, lbl_color, has_more, lbl_bold)

    # OPD SERVICE GRID
    service_widgets       = {}
    current_displayed_ids = []

    def rebuild_grid(services_to_display):
        if not is_active["value"]:
            return
        try:
            for w in opd_frame.winfo_children():
                try:
                    w.destroy()
                except:
                    pass
            service_widgets.clear()

            if not services_to_display:
                ef = tk.Frame(opd_frame, bg="#F4F6F8")
                ef.place(relx=0.5, rely=0.5, anchor="center")
                tk.Label(ef, text="⚕️", font=("Segoe UI", 48),
                         bg="#F4F6F8", fg="#9E9E9E").pack(pady=(0, 10))
                tk.Label(ef, text="No OPD Services Available",
                         font=("Segoe UI", 18, "bold"),
                         bg="#F4F6F8", fg="#E53935").pack(pady=(0, 5))
                tk.Label(ef, text="Please add services in OPD Services Management",
                         font=("Segoe UI", 12), bg="#F4F6F8", fg="#757575").pack()
                return

            current_row_frame = None
            for idx, svc in enumerate(services_to_display[:9]):
                if not is_active["value"]:
                    break
                if idx % 3 == 0:
                    current_row_frame = tk.Frame(opd_frame, bg="#F4F6F8")
                    current_row_frame.pack(side="top", fill="x",
                                           pady=(box_pady, box_pady))

                sid   = svc["service_id"]
                name  = svc["service_name"]
                color = svc.get("color", "#1E88E5")

                border_thickness = max(3, int(box_ref * 0.028))

                shadow = tk.Frame(current_row_frame, bg="#B0BEC5",
                                  width=box_width + 6, height=box_height + 6)
                shadow.pack(side="left", padx=(box_padx, box_padx))
                shadow.pack_propagate(False)

                card = tk.Frame(shadow, bg=color,
                                width=box_width, height=box_height)
                card.place(x=3, y=3)
                card.pack_propagate(False)

                inner_card = tk.Frame(card, bg="white")
                inner_card.place(x=border_thickness, y=border_thickness,
                                 width=box_width  - border_thickness * 2,
                                 height=box_height - border_thickness * 2)
                inner_card.pack_propagate(False)

                next_h = max(28, int(box_height * 0.22))
                next_canvas = tk.Canvas(inner_card, bg="white", height=next_h,
                                        highlightthickness=0, bd=0)
                next_canvas.pack(side="bottom", fill="x",
                                 padx=max(4, int(box_width * 0.04)),
                                 pady=(max(2, int(box_height * 0.010)),
                                       max(8, int(box_height * 0.050))))

                title_frame = tk.Frame(inner_card, bg="white")
                title_frame.pack(fill="x", padx=6, pady=(max(2, int(box_height * 0.03)), 0))

                tk.Label(title_frame, text=name,
                         font=("Segoe UI", service_title_size, "bold"),
                         bg="white", fg="#1A237E",
                         wraplength=box_width - 30).pack(anchor="center")

                mid = tk.Frame(inner_card, bg="white")
                mid.pack(fill="x", expand=False,
                         padx=max(4, int(box_width * 0.04)),
                         pady=(max(1, int(box_height * 0.02)), 0))

                serving_lbl = tk.Label(mid, text="---",
                                       font=("Segoe UI", serving_size, "bold"),
                                       bg="white", fg="#1A237E")
                serving_lbl.pack(side="left", anchor="w")

                waiting_lbl = tk.Label(mid, text="0",
                                       font=("Segoe UI", waiting_size, "bold"),
                                       bg="white", fg="#E53935")
                waiting_lbl.pack(side="right", anchor="e")

                bot = tk.Frame(inner_card, bg="white")
                bot.pack(fill="x",
                         padx=max(4, int(box_width * 0.04)),
                         pady=(0, max(1, int(box_height * 0.010))))

                tk.Label(bot, text="Currently Serving",
                         font=("Segoe UI", label_size),
                         bg="white", fg="#546E7A").pack(side="left", anchor="w")
                tk.Label(bot, text="Waiting",
                         font=("Segoe UI", label_size),
                         bg="white", fg="#546E7A").pack(side="right", anchor="e")

                service_widgets[sid] = {
                    "serving_label": serving_lbl,
                    "waiting_label": waiting_lbl,
                    "next_canvas":   next_canvas,
                }

        except Exception as e:
            print(f"[ERROR] rebuild_grid: {e}")

    # DATA FETCH

    def _fetch_all_data():
        """
        Runs in a background thread.
        Fetches admitting data, services, AND the server-side call state.
        The call state fetch is what makes the rotation work across 2 laptops.
        """
        if not is_active["value"]:
            return
        admitting_result   = {}
        services_result    = []
        server_call_state  = None   # ← NEW: fetched from server, not local memory

        try:
            r = requests.get(f"{API_BASE_URL}/display/admitting", timeout=2)
            if r.status_code == 200:
                d = r.json()
                if d.get("success"):
                    admitting_result = d.get("admitting", {})
        except Exception as e:
            print(f"[VIEWING] admitting fetch error: {e}")

        try:
            r = requests.get(f"{API_BASE_URL}/display/services", timeout=2)
            if r.status_code == 200:
                d = r.json()
                if d.get("success"):
                    services_result = d.get("services", [])
        except Exception as e:
            print(f"[VIEWING] services fetch error: {e}")

        try:
            r = requests.get(f"{API_BASE_URL}/call-state", timeout=1)
            if r.status_code == 200:
                d = r.json()
                if d.get("success"):
                    server_call_state = d.get("queue_type")
        except Exception as e:
            print(f"[VIEWING] call-state fetch error: {e}")

        try:
            parent.after(0, lambda: _apply_data(
                admitting_result, services_result, server_call_state))
        except:
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
            except:
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
            except:
                pass

        _update_slot3_from_data(server_call_state)

        show    = services[:9]
        new_ids = [s["service_id"] for s in show]

        nonlocal current_displayed_ids
        if new_ids != current_displayed_ids:
            rebuild_grid(show)
            current_displayed_ids = new_ids

        for svc in show:
            sid = svc["service_id"]
            if sid not in service_widgets:
                continue
            try:
                if not service_widgets[sid]["serving_label"].winfo_exists():
                    continue
            except:
                continue
            try:
                service_widgets[sid]["serving_label"].config(
                    text=str(svc.get("serving") or "---"))
                service_widgets[sid]["waiting_label"].config(
                    text=str(svc.get("waiting", 0)))
                _update_next_canvas(service_widgets[sid]["next_canvas"],
                                    svc.get("next_tickets", []))
            except:
                pass

    def schedule_next_fetch():
        def _trigger():
            if is_active["value"]:
                threading.Thread(target=_fetch_all_data, daemon=True).start()
                safe_after(refresh_interval, schedule_next_fetch)
        safe_after(refresh_interval, _trigger)

    threading.Thread(target=_fetch_all_data, daemon=True).start()
    schedule_next_fetch()

    print("[VIEWING SCREEN] Frame loaded — threaded updates active.")