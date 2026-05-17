import tkinter as tk
from tkinter import ttk, messagebox
import requests
from datetime import datetime
import pyttsx3
import threading

from config import API_BASE_URL, REQUEST_TIMEOUT, FAST_TIMEOUT
import call_state

# NUMBER-TO-WORDS HELPER

_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
_TENS = [
    "", "", "Twenty", "Thirty", "Forty", "Fifty",
    "Sixty", "Seventy", "Eighty", "Ninety",
]


def _number_to_words(n: int) -> str:
    """Return English words for a number 0–999."""
    if n == 0:
        return "Zero"
    parts = []
    if n >= 100:
        parts.append(_ONES[n // 100] + " Hundred")
        n %= 100
    if n >= 20:
        tens_word = _TENS[n // 10]
        ones_word = _ONES[n % 10]
        parts.append((tens_word + " " + ones_word).strip())
    elif n > 0:
        parts.append(_ONES[n])
    return " ".join(parts)


def _ticket_to_speech(ticket_number: str) -> str:
    if ticket_number.startswith("SL"):
        queue_label = "Special Lane"
        num_str = ticket_number[2:]
    elif ticket_number.startswith("AB"):
        queue_label = "A B T C"
        num_str = ticket_number[2:]
    elif ticket_number.startswith("P"):
        queue_label = "Priority"
        num_str = ticket_number[1:]
    elif ticket_number.startswith("R"):
        queue_label = "Regular"
        num_str = ticket_number[1:]
    else:
        digits = {"0": "Zero", "1": "One", "2": "Two", "3": "Three", "4": "Four",
                  "5": "Five", "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine"}
        return " ".join(digits.get(d, d) for d in ticket_number)

    try:
        number_words = _number_to_words(int(num_str))
    except ValueError:
        number_words = num_str

    return f"{queue_label} - Number - {number_words}"


def speak_ticket_number(ticket_number, queue_type):
    """TTS announcement — always runs in its own thread, never blocks UI."""
    def _speak():
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", 150)
            engine.setProperty("volume", 1.0)
            for v in engine.getProperty("voices"):
                if "female" in v.name.lower() or "zira" in v.name.lower():
                    engine.setProperty("voice", v.id)
                    break

            announcement = _ticket_to_speech(ticket_number)
            print(f"[ADMITTING TTS] Saying: {announcement!r}")

            for _ in range(3):
                engine.say(announcement)
                engine.runAndWait()
            engine.stop()
        except Exception as e:
            print(f"[TTS ERROR] {e}")

    threading.Thread(target=_speak, daemon=True).start()

# QUEUE TYPES CONFIG

_QUEUE_COLORS = {
    "Regular":      "#2E7D32",
    "Priority":     "#C62828",
    "Special Lane": "#1565C0",
    "ABTC":         "#F9A825",
}

_QUEUE_HOVER = {
    "Regular":      "#1B5E20",
    "Priority":     "#B71C1C",
    "Special Lane": "#0D47A1",
    "ABTC":         "#F57F17",
}

ALL_QUEUE_TYPES  = ["Regular", "Priority", "Special Lane", "ABTC"]
OPD_QUEUE_TYPES  = {"Regular", "Priority", "Special Lane"}
ABTC_QUEUE_TYPE  = "ABTC"

# ABTC colors
_ABTC_COLOR       = "#F9A825"
_ABTC_HOVER       = "#F57F17"
_ABTC_LIGHT       = "#FFF8E1"


def admitting_frame(parent):
    """STEP 2: Admitting Module — all API calls non-blocking."""
    print("[ADMITTING] Loading admitting frame...")

    for widget in parent.winfo_children():
        widget.destroy()

    _active   = {"value": True}
    _after_id = {"id": None}

    def _cleanup():
        _active["value"] = False
        if _after_id["id"]:
            try:
                parent.after_cancel(_after_id["id"])
            except:
                pass

    parent.bind("<Destroy>", lambda e: _cleanup() if e.widget == parent else None)

    # LAYOUT
    main_frame = tk.Frame(parent, bg="#F4F6F8")
    main_frame.pack(fill="both", expand=True, padx=15, pady=15)

    # Left column
    left_frame = tk.Frame(main_frame, bg="#F4F6F8", width=220)
    left_frame.pack(side="left", fill="y", padx=(0, 15))
    left_frame.pack_propagate(False)

    # Right side: two columns — Redo Table + Activity
    right_frame = tk.Frame(main_frame, bg="#F4F6F8")
    right_frame.pack(side="left", fill="both", expand=True)

    redo_frame = tk.Frame(right_frame, bg="#F4F6F8")
    redo_frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

    activity_frame = tk.Frame(right_frame, bg="#F4F6F8")
    activity_frame.pack(side="left", fill="both", expand=True)

    # HELPERS
    _boxes_container = tk.Frame(left_frame, bg="#F4F6F8")
    _boxes_container.pack(fill="both", expand=True)
    for i in range(4):
        _boxes_container.rowconfigure(i, weight=1, uniform="qbox")
    _boxes_container.columnconfigure(0, weight=1)

    _box_row = [0]

    def card_box(parent_widget):
        """Each card is gridded into _boxes_container with equal height."""
        row = _box_row[0]
        _box_row[0] += 1
        shadow = tk.Frame(_boxes_container, bg="#DADDE1")
        shadow.grid(row=row, column=0, sticky="nsew", pady=3)
        shadow.rowconfigure(0, weight=1)
        shadow.columnconfigure(0, weight=1)
        c = tk.Frame(shadow, bg="white", padx=10, pady=4)
        c.grid(row=0, column=0, padx=3, pady=3, sticky="nsew")
        return c

    def card_fill(parent_widget):
        shadow = tk.Frame(parent_widget, bg="#DADDE1")
        shadow.pack(fill="both", expand=True, pady=3)
        c = tk.Frame(shadow, bg="white", padx=10, pady=4)
        c.pack(padx=3, pady=3, fill="both", expand=True)
        return c

    # LEFT COLUMN: Queue Boxes
    current_tickets      = {qt: None for qt in ALL_QUEUE_TYPES}
    ticket_labels        = {}
    name_labels          = {}
    waiting_count_labels = {}
    action_buttons       = {}
    skip_buttons         = {}
    _btn_cooldown        = {}

    _font_widgets = []   # list of (widget, role)

    ACTION_COOLDOWN_MS = 2000

    def _start_cooldown(queue_type):
        if queue_type not in action_buttons:
            return
        btn, normal_bg, _ = action_buttons[queue_type]
        _btn_cooldown[queue_type] = True
        try:
            btn.config(state="disabled", bg="#BDBDBD")
        except Exception:
            pass
        if queue_type in skip_buttons:
            try:
                skip_buttons[queue_type].config(state="disabled", bg="#BDBDBD")
            except Exception:
                pass
        def _reenable():
            _btn_cooldown[queue_type] = False
            try:
                btn.config(state="normal", bg=normal_bg)
            except Exception:
                pass
            if queue_type in skip_buttons:
                try:
                    skip_buttons[queue_type].config(state="normal", bg="#FB8C00")
                except Exception:
                    pass
        parent.after(ACTION_COOLDOWN_MS, _reenable)

    def _make_queue_box(queue_type):
        color = _QUEUE_COLORS[queue_type]
        hover = _QUEUE_HOVER[queue_type]

        box = card_box(left_frame)

        box.rowconfigure(0, weight=1)   # content row expands
        box.rowconfigure(1, weight=0)   # button row fixed
        box.columnconfigure(0, weight=1)

        # Content frame
        content = tk.Frame(box, bg="white")
        content.grid(row=0, column=0, sticky="nsew")

        # Title row
        title_row = tk.Frame(content, bg="white")
        title_row.pack(fill="x", pady=(2, 2))

        dot_lbl = tk.Label(title_row, text="●", font=("Segoe UI", 12),
                           bg="white", fg=color)
        dot_lbl.pack(side="left")
        _font_widgets.append((dot_lbl, "dot"))

        type_lbl = tk.Label(title_row, text=f"  {queue_type}",
                            font=("Segoe UI", 13, "bold"),
                            bg="white", fg=color)
        type_lbl.pack(side="left")
        _font_widgets.append((type_lbl, "title"))

        tl = tk.Label(content, text="Loading...", font=("Segoe UI", 16, "bold"),
                      bg="white", fg="#9E9E9E")
        tl.pack(pady=(2, 0))
        ticket_labels[queue_type] = tl
        _font_widgets.append((tl, "ticket"))

        nl = tk.Label(content, text="", font=("Segoe UI", 11),
                      bg="white", fg="#546E7A")
        nl.pack(pady=(1, 0))
        name_labels[queue_type] = nl
        _font_widgets.append((nl, "name"))

        wl = tk.Label(content, text="", font=("Segoe UI", 9),
                      bg="white", fg="#263238")
        wl.pack(pady=(1, 2))
        waiting_count_labels[queue_type] = wl
        _font_widgets.append((wl, "count"))

        # Button row
        btn_frame = tk.Frame(box, bg="white")
        btn_frame.grid(row=1, column=0, sticky="ew", pady=(0, 3))

        call_btn = tk.Button(btn_frame, text="📢 Call",
                             font=("Segoe UI", 10, "bold"),
                             bg="#9C27B0", fg="white", bd=0,
                             padx=4, pady=5, cursor="hand2",
                             command=lambda qt=queue_type: call_ticket(qt))
        call_btn.pack(side="left", expand=True, fill="x", padx=(0, 2))
        call_btn.bind("<Enter>", lambda e, b=call_btn: b.config(bg="#7B1FA2"))
        call_btn.bind("<Leave>", lambda e, b=call_btn: b.config(bg="#9C27B0"))
        _font_widgets.append((call_btn, "btn"))

        skip_btn = tk.Button(btn_frame, text="⏭ Skip",
                             font=("Segoe UI", 10, "bold"),
                             bg="#FB8C00", fg="white", bd=0,
                             padx=4, pady=5, cursor="hand2",
                             command=lambda qt=queue_type: skip_ticket(qt))
        skip_btn.pack(side="left", expand=True, fill="x", padx=(0, 2))
        skip_btn.bind("<Enter>", lambda e, b=skip_btn: b.config(bg="#EF6C00"))
        skip_btn.bind("<Leave>", lambda e, b=skip_btn: b.config(bg="#FB8C00"))
        skip_buttons[queue_type] = skip_btn
        _font_widgets.append((skip_btn, "btn"))

        if queue_type == ABTC_QUEUE_TYPE:
            action_text  = "✔ ABTC"
            action_bg    = "#00838F"
            action_hover = "#00695C"
            action_cmd   = lambda qt=queue_type: send_to_abtc_done(qt)
        else:
            action_text  = "➡ OPD"
            action_bg    = "#43A047"
            action_hover = "#2E7D32"
            action_cmd   = lambda qt=queue_type: send_to_opd(qt)

        action_btn = tk.Button(btn_frame, text=action_text,
                               font=("Segoe UI", 10, "bold"),
                               bg=action_bg, fg="white", bd=0,
                               padx=4, pady=5, cursor="hand2",
                               command=action_cmd)
        action_btn.pack(side="left", expand=True, fill="x")
        action_btn.bind("<Enter>", lambda e, b=action_btn, h=action_hover: b.config(bg=h))
        action_btn.bind("<Leave>", lambda e, b=action_btn, bg=action_bg: b.config(bg=bg))
        _font_widgets.append((action_btn, "btn"))

        action_buttons[queue_type] = (action_btn, action_bg, action_hover)
        _btn_cooldown[queue_type]  = False

    # Build all 4 boxes
    for qt in ALL_QUEUE_TYPES:
        _make_queue_box(qt)

    _last_h = {"v": 0}

    def _rescale_fonts(event=None):
        h = parent.winfo_height()
        if h < 50 or abs(h - _last_h["v"]) < 4:
            return
        _last_h["v"] = h

        box_h = max(60, (h - 30 - 4 * 6) / 4)

        dot_sz    = max(7,  min(12, int(box_h * 0.11)))
        title_sz  = max(7,  min(13, int(box_h * 0.11)))
        ticket_sz = max(9,  min(18, int(box_h * 0.16)))
        name_sz   = max(7,  min(11, int(box_h * 0.09)))
        count_sz  = max(6,  min(9,  int(box_h * 0.07)))
        btn_sz    = max(7,  min(10, int(box_h * 0.08)))
        btn_pady  = max(2,  min(6,  int(box_h * 0.04)))

        for widget, role in _font_widgets:
            try:
                if role == "dot":
                    widget.config(font=("Segoe UI", dot_sz))
                elif role == "title":
                    widget.config(font=("Segoe UI", title_sz, "bold"))
                elif role == "ticket":
                    widget.config(font=("Segoe UI", ticket_sz, "bold"))
                elif role == "name":
                    widget.config(font=("Segoe UI", name_sz))
                elif role == "count":
                    widget.config(font=("Segoe UI", count_sz))
                elif role == "btn":
                    widget.config(font=("Segoe UI", btn_sz, "bold"), pady=btn_pady)
            except Exception:
                pass

    parent.bind("<Configure>", _rescale_fonts)

    # RIGHT: Recent Activity
    history_shadow = tk.Frame(activity_frame, bg="#DADDE1")
    history_shadow.pack(fill="both", expand=True, pady=8)
    history_box = tk.Frame(history_shadow, bg="white", padx=15, pady=12)
    history_box.pack(padx=3, pady=3, fill="both", expand=True)

    tk.Label(history_box, text="Recent Activity",
             font=("Segoe UI", 14, "bold"), bg="white", fg="#263238").pack(pady=(0, 10))

    style = ttk.Style()
    style.configure("Admitting.Treeview", font=("Segoe UI", 10), rowheight=28,
                    background="white", fieldbackground="white")
    style.configure("Admitting.Treeview.Heading",
                    font=("Segoe UI", 10, "bold"),
                    background="#E3F2FD", foreground="#1E88E5")
    style.map("Admitting.Treeview", background=[("selected", "#1E88E5")])

    tree_frame = tk.Frame(history_box, bg="white")
    tree_frame.pack(fill="both", expand=True)

    columns = ("Ticket", "Service", "Status", "Time", "Action")
    tree = ttk.Treeview(tree_frame, columns=columns, show="headings",
                        style="Admitting.Treeview")
    tree.pack(side="left", fill="both", expand=True)
    scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")

    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, anchor="center", width=130, stretch=True)

    refresh_btn = tk.Button(history_box, text="🔄 Refresh",
                            font=("Segoe UI", 10, "bold"),
                            bg="#1E88E5", fg="white", bd=0,
                            padx=15, pady=6, cursor="hand2",
                            command=lambda: (load_tickets(), load_history()))
    refresh_btn.pack(pady=(10, 0))
    refresh_btn.bind("<Enter>", lambda e: refresh_btn.config(bg="#1565C0"))
    refresh_btn.bind("<Leave>", lambda e: refresh_btn.config(bg="#1E88E5"))

    # ──────────────────────────────────────────────────────────────────────────
    # RIGHT REDO COLUMN: ABTC Ticket Creation (top half) + Skipped Tickets (bottom half)
    # ──────────────────────────────────────────────────────────────────────────

    # ABTC TICKET CREATION BOX
    abtc_shadow = tk.Frame(redo_frame, bg="#DADDE1")
    abtc_shadow.pack(fill="x", pady=(8, 4))
    abtc_box = tk.Frame(abtc_shadow, bg="white", padx=15, pady=10)
    abtc_box.pack(padx=3, pady=3, fill="x")

    # Header band
    abtc_hdr = tk.Frame(abtc_box, bg=_ABTC_COLOR, height=36)
    abtc_hdr.pack(fill="x", pady=(0, 10))
    abtc_hdr.pack_propagate(False)
    tk.Label(abtc_hdr, text="⚕  ABTC — Create Ticket",
             font=("Segoe UI", 11, "bold"), bg=_ABTC_COLOR, fg="white").pack(
        side="left", padx=10, pady=6)

    # Input row
    input_row = tk.Frame(abtc_box, bg="white")
    input_row.pack(fill="x", pady=(0, 8))

    # Ticket number
    tk.Label(input_row, text="No.:", font=("Segoe UI", 10, "bold"),
             bg="white", fg="#37474F").pack(side="left", padx=(0, 4))
    abtc_ticket_entry = ttk.Entry(input_row, width=6, justify="center",
                                   font=("Segoe UI", 11))
    abtc_ticket_entry.pack(side="left", ipady=4, padx=(0, 12))
    abtc_ticket_entry.insert(0, "001")

    # Patient name
    tk.Label(input_row, text="Name:", font=("Segoe UI", 10, "bold"),
             bg="white", fg="#37474F").pack(side="left", padx=(0, 4))
    abtc_name_entry = ttk.Entry(input_row, width=18, justify="left",
                                 font=("Segoe UI", 11))
    abtc_name_entry.pack(side="left", ipady=4, padx=(0, 10), fill="x", expand=True)

    # Send button
    abtc_send_btn = tk.Button(
        input_row, text="Send",
        font=("Segoe UI", 10, "bold"),
        bg=_ABTC_COLOR, fg="white", bd=0,
        padx=10, pady=4, cursor="hand2",
    )
    abtc_send_btn.pack(side="left")
    abtc_send_btn.bind("<Enter>", lambda e: abtc_send_btn.config(bg=_ABTC_HOVER))
    abtc_send_btn.bind("<Leave>", lambda e: abtc_send_btn.config(bg=_ABTC_COLOR))

    # Status label
    abtc_status_lbl = tk.Label(abtc_box, text="",
                                font=("Segoe UI", 9), bg="white", fg="#388E3C")
    abtc_status_lbl.pack(anchor="w")

    def _fetch_next_abtc():
        """Fetch the next ABTC ticket number from server and update the entry."""
        def _fetch():
            try:
                r = requests.get(
                    f"{API_BASE_URL}/tickets/list",
                    params={"today_only": "true"},
                    timeout=FAST_TIMEOUT
                )
                if r.status_code == 200:
                    data = r.json()
                    if data.get("success"):
                        tickets = data.get("tickets", [])
                        max_num = 0
                        for t in tickets:
                            if t.get("queue_type") != "ABTC":
                                continue
                            dtn = t.get("display_ticket_number", "") or ""
                            if "-" in dtn:
                                continue
                            if dtn.startswith("AB"):
                                try:
                                    val = int(dtn[2:])
                                    if val > max_num:
                                        max_num = val
                                except (ValueError, IndexError):
                                    pass
                        next_num = max_num + 1
                        def _apply():
                            try:
                                abtc_ticket_entry.delete(0, tk.END)
                                abtc_ticket_entry.insert(0, f"{next_num:03d}")
                            except Exception:
                                pass
                        parent.after(0, _apply)
            except Exception as e:
                print(f"[ADMITTING ABTC] fetch_next error: {e}")
        threading.Thread(target=_fetch, daemon=True).start()

    def _create_abtc_ticket():
        ticket_num   = abtc_ticket_entry.get().strip()
        patient_name = abtc_name_entry.get().strip()

        if not ticket_num:
            messagebox.showerror("Error", "Please enter a ticket number", parent=parent)
            return
        if not ticket_num.isdigit() or len(ticket_num) != 3:
            messagebox.showerror("Error", "Ticket number must be exactly 3 digits (e.g., 001)",
                                 parent=parent)
            return

        abtc_send_btn.config(state="disabled", text="Sending...")
        abtc_status_lbl.config(text="")
        manual_num = int(ticket_num)

        def _post():
            try:
                r = requests.post(
                    f"{API_BASE_URL}/tickets/create",
                    json={
                        "patient_name":     patient_name if patient_name else None,
                        "queue_type":       "ABTC",
                        "requested_number": manual_num,
                        "force_number":     True,
                    },
                    timeout=REQUEST_TIMEOUT
                )
                if r.status_code == 200:
                    data = r.json()
                    if data.get("success"):
                        created = data.get("ticket_number")
                        print(f"[ADMITTING ABTC] Created ticket: {created}")

                        def _on_success():
                            abtc_status_lbl.config(
                                text=f"✔  Created: {created}",
                                fg="#388E3C"
                            )
                            abtc_name_entry.delete(0, tk.END)
                            abtc_send_btn.config(state="normal", text="Send")
                            _fetch_next_abtc()
                            load_tickets()
                            load_history()

                        parent.after(0, _on_success)
                        return
                    else:
                        err = data.get("message", "Failed to create ABTC ticket")
                        parent.after(0, lambda: (
                            messagebox.showerror("Error", err, parent=parent),
                            abtc_send_btn.config(state="normal", text="Send")
                        ))
                else:
                    parent.after(0, lambda: (
                        messagebox.showerror("Error", f"Server error: {r.status_code}", parent=parent),
                        abtc_send_btn.config(state="normal", text="Send")
                    ))
            except requests.exceptions.ConnectionError:
                parent.after(0, lambda: (
                    messagebox.showerror("Connection Error",
                        f"Cannot connect to server at:\n{API_BASE_URL}", parent=parent),
                    abtc_send_btn.config(state="normal", text="Send")
                ))
            except Exception as e:
                parent.after(0, lambda: (
                    messagebox.showerror("Error", f"Failed: {e}", parent=parent),
                    abtc_send_btn.config(state="normal", text="Send")
                ))

        threading.Thread(target=_post, daemon=True).start()

    abtc_send_btn.config(command=_create_abtc_ticket)

    # Fetch initial ABTC ticket number
    _fetch_next_abtc()

    # SKIPPED TICKETS BOX
    redo_shadow = tk.Frame(redo_frame, bg="#DADDE1")
    redo_shadow.pack(fill="both", expand=True, pady=(4, 8))
    redo_box = tk.Frame(redo_shadow, bg="white", padx=15, pady=12)
    redo_box.pack(padx=3, pady=3, fill="both", expand=True)

    tk.Label(redo_box, text="Skipped Tickets",
             font=("Segoe UI", 14, "bold"), bg="white", fg="#263238").pack(pady=(0, 4))
    tk.Label(redo_box, text="Select a row then click Redo to re-serve",
             font=("Segoe UI", 8, "italic"), bg="white", fg="#9E9E9E").pack(pady=(0, 8))

    redo_style = ttk.Style()
    redo_style.configure("AdmittingRedo.Treeview",        font=("Segoe UI", 10), rowheight=28,
                         background="white", fieldbackground="white")
    redo_style.configure("AdmittingRedo.Treeview.Heading",
                         font=("Segoe UI", 10, "bold"),
                         background="#FFF3E0", foreground="#E65100")
    redo_style.map("AdmittingRedo.Treeview", background=[("selected", "#FB8C00")])

    redo_tree_frame = tk.Frame(redo_box, bg="white")
    redo_tree_frame.pack(fill="both", expand=True)

    redo_cols = ("Ticket", "Queue Type", "Time")
    redo_tree = ttk.Treeview(redo_tree_frame, columns=redo_cols,
                             show="headings", style="AdmittingRedo.Treeview")
    redo_tree.pack(side="left", fill="both", expand=True)

    redo_scroll = ttk.Scrollbar(redo_tree_frame, orient="vertical", command=redo_tree.yview)
    redo_tree.configure(yscrollcommand=redo_scroll.set)
    redo_scroll.pack(side="right", fill="y")

    redo_tree.heading("Ticket",     text="Ticket");     redo_tree.column("Ticket",     width=90,  anchor="center")
    redo_tree.heading("Queue Type", text="Queue Type"); redo_tree.column("Queue Type", width=110, anchor="center")
    redo_tree.heading("Time",       text="Time");       redo_tree.column("Time",       width=80,  anchor="center")

    _redo_ticket_ids = {}

    redo_btn = tk.Button(
        redo_box, text="↩  Redo Selected",
        font=("Segoe UI", 10, "bold"),
        bg="#FB8C00", fg="white", bd=0,
        padx=8, pady=8, cursor="hand2"
    )
    redo_btn.pack(fill="x", pady=(10, 0))
    redo_btn.bind("<Enter>", lambda e: redo_btn.config(bg="#EF6C00"))
    redo_btn.bind("<Leave>", lambda e: redo_btn.config(bg="#FB8C00"))

    # API HELPERS

    def load_tickets():
        def _fetch():
            try:
                r = requests.get(
                    f"{API_BASE_URL}/tickets/list?stage=1&status=Waiting&today_only=true",
                    timeout=FAST_TIMEOUT
                )
                if r.status_code == 200:
                    data = r.json()
                    if data.get("success"):
                        tickets = data.get("tickets", [])
                        parent.after(0, lambda: _apply_tickets(tickets))
                        return
            except Exception as e:
                print(f"[ADMITTING] load_tickets error: {e}")
        threading.Thread(target=_fetch, daemon=True).start()

    def load_waiting_counts():
        """Fetch waiting counts per queue type from /api/display/admitting."""
        def _fetch():
            try:
                r = requests.get(f"{API_BASE_URL}/display/admitting", timeout=FAST_TIMEOUT)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("success"):
                        admitting = data.get("admitting", {})
                        parent.after(0, lambda: _apply_waiting_counts(admitting))
            except Exception as e:
                print(f"[ADMITTING] load_waiting_counts error: {e}")
        threading.Thread(target=_fetch, daemon=True).start()

    def _apply_waiting_counts(admitting):
        if not _active["value"]:
            return
        for qt in ALL_QUEUE_TYPES:
            lbl = waiting_count_labels.get(qt)
            if not lbl:
                continue
            try:
                info    = admitting.get(qt, {})
                waiting = int(info.get("waiting", 0))
                if waiting > 0:
                    lbl.config(text=f"Waiting: {waiting}")
                else:
                    lbl.config(text="")
            except Exception:
                pass

    def _apply_tickets(tickets):
        if not _active["value"]:
            return
        for qt in ALL_QUEUE_TYPES:
            ticket_data = next((t for t in tickets if t.get("queue_type") == qt), None)
            current_tickets[qt] = ticket_data
            if ticket_data:
                display_num = (
                    ticket_data.get("display_ticket_number")
                    or ticket_data.get("ticket_number", "")
                )
                color = _QUEUE_COLORS.get(qt, "#1E88E5")
                ticket_labels[qt].config(
                    text=display_num,
                    fg=color, font=("Segoe UI", 16, "bold"))
                name_labels[qt].config(
                    text=ticket_data.get("patient_name") or "No Name",
                    fg="#546E7A", font=("Segoe UI", 11))
            else:
                ticket_labels[qt].config(
                    text="No ticket", fg="#9E9E9E",
                    font=("Segoe UI", 11, "italic"))
                name_labels[qt].config(text="", fg="#9E9E9E")
        load_waiting_counts()

    def load_history():
        def _fetch():
            try:
                today = datetime.now().strftime("%b %d, %Y")
                r = requests.get(
                    f"{API_BASE_URL}/activity/list?date={today}",
                    timeout=FAST_TIMEOUT
                )
                if r.status_code == 200:
                    data = r.json()
                    if data.get("success"):
                        parent.after(0, lambda: _apply_history(data.get("logs", [])))
            except Exception as e:
                print(f"[ADMITTING] load_history error: {e}")
        threading.Thread(target=_fetch, daemon=True).start()

    def _apply_history(logs):
        if not _active["value"]:
            return
        try:
            tree.delete(*tree.get_children())
            if not logs:
                tree.insert("", "end", values=("", "No activity yet", "", "", ""))
            else:
                for log in logs:
                    tree.insert("", "end", values=(
                        log.get("ticket_number"), log.get("service_name"),
                        log.get("status"), log.get("time"), log.get("action")))
                tree.yview_moveto(0)
        except:
            pass

    def load_skipped_tickets():
        """Load today's skipped Stage-1 tickets into the Redo table."""
        def _fetch():
            try:
                r = requests.get(
                    f"{API_BASE_URL}/tickets/list",
                    params={"status": "Skipped", "today_only": "true"},
                    timeout=FAST_TIMEOUT
                )
                if r.status_code == 200:
                    d = r.json()
                    if d.get("success"):
                        tickets = [t for t in d.get("tickets", []) if t.get("stage") == 1]
                        parent.after(0, lambda: _apply_skipped(tickets))
            except Exception as e:
                print(f"[ADMITTING] load_skipped_tickets error: {e}")
        threading.Thread(target=_fetch, daemon=True).start()

    def _apply_skipped(tickets):
        if not _active["value"]:
            return
        try:
            previously_selected_id = None
            sel = redo_tree.selection()
            if sel:
                prev_info = _redo_ticket_ids.get(sel[0])
                if prev_info:
                    previously_selected_id = prev_info["ticket_id"]

            redo_tree.delete(*redo_tree.get_children())
            _redo_ticket_ids.clear()

            restore_iid = None
            for t in reversed(tickets):
                display_num = t.get("display_ticket_number") or t.get("ticket_number", "")
                queue_type  = t.get("queue_type", "Regular")
                raw_time = t.get("updated_at") or t.get("created_at") or ""
                time_str = "---"
                if raw_time:
                    clean = raw_time.replace("T", " ").split("+")[0].rstrip("Z").strip()
                    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
                        try:
                            from datetime import timedelta
                            dt = datetime.strptime(clean, fmt) + timedelta(hours=8)
                            time_str = dt.strftime("%H:%M:%S")
                            break
                        except ValueError:
                            pass
                iid = redo_tree.insert("", "end",
                                       values=(display_num, queue_type, time_str))
                _redo_ticket_ids[iid] = {
                    "ticket_id":    t.get("ticket_id"),
                    "display_num":  display_num,
                    "queue_type":   queue_type,
                }
                if t.get("ticket_id") == previously_selected_id:
                    restore_iid = iid

            if restore_iid:
                redo_tree.selection_set(restore_iid)
                redo_tree.see(restore_iid)

        except Exception as e:
            print(f"[ADMITTING] _apply_skipped error: {e}")

    # ACTIONS

    def call_ticket(queue_type):
        ticket = current_tickets.get(queue_type)
        if not ticket:
            messagebox.showinfo("No Ticket", f"No {queue_type} ticket in queue.", parent=parent)
            return
        display_num = (
            ticket.get("display_ticket_number")
            or ticket.get("ticket_number", "")
        )

        if queue_type in ("Special Lane", "ABTC"):
            call_state.set_called(queue_type)

        speak_ticket_number(display_num, queue_type)

    def skip_ticket(queue_type):
        if _btn_cooldown.get(queue_type):
            return
        ticket = current_tickets.get(queue_type)
        if not ticket:
            messagebox.showinfo("No Ticket", f"No {queue_type} ticket to skip.", parent=parent)
            return

        _start_cooldown(queue_type)

        ticket_id   = ticket.get("ticket_id")
        display_num = (
            ticket.get("display_ticket_number")
            or ticket.get("ticket_number", "")
        )

        def _put():
            try:
                r = requests.put(
                    f"{API_BASE_URL}/tickets/{ticket_id}/update",
                    json={"status": "Skipped"},
                    timeout=REQUEST_TIMEOUT
                )
                if r.status_code == 200 and r.json().get("success"):
                    parent.after(0, lambda: (
                        load_tickets(),
                        load_history(),
                        load_skipped_tickets(),
                    ))
                else:
                    parent.after(0, lambda: messagebox.showerror(
                        "Error", "Failed to skip ticket", parent=parent))
            except Exception as e:
                parent.after(0, lambda: messagebox.showerror(
                    "Error", f"Connection error: {e}", parent=parent))

        threading.Thread(target=_put, daemon=True).start()

    def redo_skipped_ticket():
        sel = redo_tree.selection()
        if not sel:
            messagebox.showwarning("No Selection",
                                   "Please click a skipped ticket row first.",
                                   parent=parent)
            return

        iid  = sel[0]
        info = _redo_ticket_ids.get(iid)
        if not info:
            return

        ticket_id   = info["ticket_id"]
        display_num = info["display_num"]
        queue_type  = info["queue_type"]

        if not messagebox.askyesno(
            "Confirm Redo",
            f"Re-serve ticket  {display_num}  ({queue_type})?\n\n"
            f"It will become the current ticket immediately.\n"
            f"Any ticket currently showing will move behind it.",
            parent=parent
        ):
            return

        redo_btn.config(state="disabled", text="⏳ Processing...")

        def _put():
            displaced_ids = []
            try:
                try:
                    r0 = requests.get(
                        f"{API_BASE_URL}/tickets/list",
                        params={"stage": 1, "status": "Waiting", "today_only": "true"},
                        timeout=FAST_TIMEOUT
                    )
                    if r0.status_code == 200 and r0.json().get("success"):
                        displaced_ids = [
                            t["ticket_id"]
                            for t in r0.json().get("tickets", [])
                            if t.get("queue_type") == queue_type
                               and t["ticket_id"] != ticket_id
                        ]
                except Exception as ex:
                    print(f"[ADMITTING REDO] fetch waiting error: {ex}")

                print(f"[ADMITTING REDO] Displacing {len(displaced_ids)} tickets temporarily")

                for wid in displaced_ids:
                    try:
                        requests.put(
                            f"{API_BASE_URL}/tickets/{wid}/update",
                            json={"status": "Skipped"},
                            timeout=REQUEST_TIMEOUT
                        )
                    except Exception:
                        pass

                r = requests.put(
                    f"{API_BASE_URL}/tickets/{ticket_id}/update",
                    json={"stage": 1, "status": "Waiting"},
                    timeout=REQUEST_TIMEOUT
                )

                if r.status_code == 200 and r.json().get("success"):
                    for wid in displaced_ids:
                        try:
                            requests.put(
                                f"{API_BASE_URL}/tickets/{wid}/update",
                                json={"stage": 1, "status": "Waiting"},
                                timeout=REQUEST_TIMEOUT
                            )
                        except Exception:
                            pass

                    def _ok():
                        redo_btn.config(state="normal", text="↩  Redo Selected")
                        load_tickets()
                        load_history()
                        load_skipped_tickets()
                    parent.after(0, _ok)

                else:
                    for wid in displaced_ids:
                        try:
                            requests.put(
                                f"{API_BASE_URL}/tickets/{wid}/update",
                                json={"stage": 1, "status": "Waiting"},
                                timeout=REQUEST_TIMEOUT
                            )
                        except Exception:
                            pass
                    def _err():
                        redo_btn.config(state="normal", text="↩  Redo Selected")
                        messagebox.showerror("Error", "Failed to re-queue ticket.", parent=parent)
                    parent.after(0, _err)

            except Exception as e:
                for wid in displaced_ids:
                    try:
                        requests.put(
                            f"{API_BASE_URL}/tickets/{wid}/update",
                            json={"stage": 1, "status": "Waiting"},
                            timeout=REQUEST_TIMEOUT
                        )
                    except Exception:
                        pass
                def _err(msg=str(e)):
                    try:
                        redo_btn.config(state="normal", text="↩  Redo Selected")
                    except Exception:
                        pass
                    messagebox.showerror("Error", f"Connection error: {msg}", parent=parent)
                parent.after(0, _err)

        threading.Thread(target=_put, daemon=True).start()

    redo_btn.config(command=redo_skipped_ticket)

    def send_to_opd(queue_type):
        if _btn_cooldown.get(queue_type):
            return
        ticket = current_tickets.get(queue_type)
        if not ticket:
            messagebox.showinfo("No Ticket", f"No {queue_type} ticket to send.", parent=parent)
            return

        _start_cooldown(queue_type)

        ticket_id     = ticket.get("ticket_id")
        ticket_number = ticket.get("ticket_number", "")

        try:
            import kiosk as _kiosk
            prefix = _kiosk.get_queue_prefix(queue_type)
            if ticket_number.startswith(prefix):
                num = int(ticket_number[len(prefix):])
                _kiosk._set_cache(queue_type, num + 1)
                print(f"[ADMITTING] Bumped kiosk cache → {queue_type}: next={(num+1):03d}")
        except Exception as ex:
            print(f"[ADMITTING] kiosk cache bump skipped: {ex}")

        def _put():
            try:
                r = requests.put(
                    f"{API_BASE_URL}/tickets/{ticket_id}/update",
                    json={"stage": 3, "status": "Ready for Service"},
                    timeout=REQUEST_TIMEOUT
                )
                if r.status_code == 200 and r.json().get("success"):
                    parent.after(0, lambda: (load_tickets(), load_history()))
                else:
                    parent.after(0, lambda: messagebox.showerror(
                        "Error", "Failed to send ticket to OPD", parent=parent))
            except Exception as e:
                parent.after(0, lambda: messagebox.showerror(
                    "Error", f"Connection error: {e}", parent=parent))

        threading.Thread(target=_put, daemon=True).start()

    def send_to_abtc_done(queue_type):
        if _btn_cooldown.get(queue_type):
            return
        ticket = current_tickets.get(queue_type)
        if not ticket:
            messagebox.showinfo("No Ticket", "No ABTC ticket in queue.", parent=parent)
            return

        _start_cooldown(queue_type)

        ticket_id   = ticket.get("ticket_id")
        display_num = (
            ticket.get("display_ticket_number")
            or ticket.get("ticket_number", "")
        )

        try:
            import kiosk as _kiosk
            prefix = _kiosk.get_queue_prefix(queue_type)
            raw_num = ticket.get("ticket_number", "") or ticket.get("display_ticket_number", "")
            if raw_num.startswith(prefix):
                num = int(raw_num[len(prefix):])
                _kiosk._set_cache(queue_type, num + 1)
                print(f"[ADMITTING] Bumped ABTC kiosk cache: next={(num+1):03d}")
        except Exception as ex:
            print(f"[ADMITTING] ABTC kiosk cache bump skipped: {ex}")

        def _put():
            try:
                r = requests.put(
                    f"{API_BASE_URL}/tickets/{ticket_id}/update",
                    json={"stage": 4, "status": "Served"},
                    timeout=REQUEST_TIMEOUT
                )
                if r.status_code == 200 and r.json().get("success"):
                    call_state.clear_called()
                    parent.after(0, lambda: (load_tickets(), load_history()))
                else:
                    parent.after(0, lambda: messagebox.showerror(
                        "Error", "Failed to process ABTC ticket", parent=parent))
            except Exception as e:
                parent.after(0, lambda: messagebox.showerror(
                    "Error", f"Connection error: {e}", parent=parent))

        threading.Thread(target=_put, daemon=True).start()

    # AUTO REFRESH
    def auto_refresh():
        if not _active["value"]:
            return
        load_tickets()
        load_history()
        load_skipped_tickets()
        _after_id["id"] = parent.after(5000, auto_refresh)

    load_tickets()
    load_history()
    load_skipped_tickets()
    _after_id["id"] = parent.after(5000, auto_refresh)

    print("[ADMITTING] Frame loaded successfully!")