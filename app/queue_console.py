import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
import requests
import pyttsx3
import threading
import time

from config import API_BASE_URL, REQUEST_TIMEOUT, FAST_TIMEOUT

# Global persistent state
last_selected_service_code = None
ticket_selections = {}

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
    part = ticket_number.split("-")[-1] if "-" in ticket_number else ticket_number

    if part.startswith("SL"):
        queue_label = "Special Lane"
        num_str = part[2:]
    elif part.startswith("P"):
        queue_label = "Priority"
        num_str = part[1:]
    elif part.startswith("R"):
        queue_label = "Regular"
        num_str = part[1:]
    else:
        digits = {"0": "Zero", "1": "One", "2": "Two", "3": "Three", "4": "Four",
                  "5": "Five", "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine"}
        return " ".join(digits.get(d, d) for d in part)

    try:
        number_words = _number_to_words(int(num_str))
    except ValueError:
        number_words = num_str

    return f"{queue_label} - Number - {number_words}"


def speak_ticket_number(ticket_number, service_name):
    def _speak():
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", 150)
            engine.setProperty("volume", 1.0)
            for v in engine.getProperty("voices"):
                if "female" in v.name.lower() or "zira" in v.name.lower():
                    engine.setProperty("voice", v.id)
                    break
            ticket_announcement = _ticket_to_speech(ticket_number)
            ann = f"{service_name}, {ticket_announcement}"
            print(f"[QUEUE CONSOLE TTS] Saying: {ann!r}")
            for _ in range(3):
                engine.say(ann)
                engine.runAndWait()
            engine.stop()
        except Exception as e:
            print(f"[TTS ERROR] {e}")
    threading.Thread(target=_speak, daemon=True).start()

def _clean_service_str(raw):
    try:
        clean = raw.strip()
        for suffix in (" ●", "●", " *", "*"):
            if clean.endswith(suffix):
                clean = clean[: -len(suffix)].strip()

        last_open = clean.rfind(" (")
        if last_open == -1:
            return None, None

        sn = clean[:last_open].strip()
        rest = clean[last_open + 2:]

        close = rest.find(")")
        if close == -1:
            sc = rest.strip()
        else:
            sc = rest[:close].strip()

        if not sn or not sc:
            return None, None

        return sn, sc
    except Exception as e:
        print(f"[QUEUE CONSOLE] _clean_service_str failed on {raw!r}: {e}")
        return None, None

# EXTRACT SERVICE CODE
def _service_code_from_ticket(ticket_number: str):
    parts = ticket_number.split("-")
    if len(parts) < 2:
        return None

    for i in range(len(parts) - 1, 0, -1):
        token = parts[i]
        if token and token[0] in ("R", "P", "S", "A"):
            code = "-".join(parts[:i])
            return code if code else None

    return None

# HELPER
def _parse_utc_to_local(raw_time: str) -> str:
    """Convert a UTC timestamp string from the server to local PHT (UTC+8) HH:MM:SS."""
    if not raw_time:
        return "---"
    clean = raw_time.replace("T", " ").split("+")[0].rstrip("Z").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(clean, fmt) + timedelta(hours=8)
            return dt.strftime("%H:%M:%S")
        except ValueError:
            pass
    return "---"


def queue_console_frame(parent_frame):
    """STEP 3: Queue Console -- fully non-blocking."""
    global last_selected_service_code, ticket_selections

    print("[QUEUE CONSOLE] Loading frame...")

    for widget in parent_frame.winfo_children():
        try:
            widget.destroy()
        except:
            pass
    try:
        parent_frame.update_idletasks()
    except:
        pass

    is_active = {"value": True}
    after_ids = []

    def safe_after(delay, func):
        if is_active["value"]:
            try:
                aid = parent_frame.after(delay, func)
                after_ids.append(aid)
                return aid
            except:
                is_active["value"] = False
        return None

    def cleanup():
        is_active["value"] = False
        for aid in after_ids:
            try:
                parent_frame.after_cancel(aid)
            except:
                pass
        after_ids.clear()

    try:
        parent_frame.bind("<Destroy>",
                          lambda e: cleanup() if e.widget == parent_frame else None)
    except:
        pass

    main_frame = tk.Frame(parent_frame, bg="#F4F6F8")
    main_frame.pack(fill="both", expand=True, padx=15, pady=15)

    left_frame = tk.Frame(main_frame, bg="#F4F6F8", width=280)
    left_frame.pack(side="left", fill="y", padx=(0, 10))
    left_frame.pack_propagate(False)

    middle_frame = tk.Frame(main_frame, bg="#F4F6F8")
    middle_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

    right_frame = tk.Frame(main_frame, bg="#F4F6F8", width=320)
    right_frame.pack(side="left", fill="both", expand=True)
    right_frame.pack_propagate(False)

    def card_box(p):
        s = tk.Frame(p, bg="#DADDE1"); s.pack(fill="x", pady=6)
        c = tk.Frame(s, bg="white", padx=12, pady=10); c.pack(padx=3, pady=3, fill="x")
        return c

    def card_fill(p):
        s = tk.Frame(p, bg="#DADDE1"); s.pack(fill="both", expand=True, pady=6)
        c = tk.Frame(s, bg="white", padx=12, pady=10); c.pack(padx=3, pady=3, fill="both", expand=True)
        return c

    # LEFT: Service Monitor
    box1 = card_box(left_frame)
    tk.Label(box1, text="Service Monitor",
             font=("Segoe UI", 13, "bold"), bg="white", fg="#263238").pack(pady=(0, 8))

    service_var      = tk.StringVar()
    serving_var      = tk.StringVar(value="Serving: None")
    waiting_var      = tk.StringVar(value="Waiting: 0")
    served_var       = tk.StringVar(value="Served: 0")
    active_services  = []
    service_dropdown = None

    focused_ticket = {"number": None, "service_code": None}

    dropdown_placeholder = tk.Frame(box1, bg="white")
    dropdown_placeholder.pack(fill="x", pady=(0, 8))
    tk.Label(dropdown_placeholder, text="Loading services...",
             font=("Segoe UI", 9, "italic"), bg="white", fg="#9E9E9E").pack(pady=5)

    stats_frame = tk.Frame(box1, bg="white")
    stats_frame.pack(fill="x", pady=(5, 0))
    tk.Label(stats_frame, textvariable=serving_var,
             font=("Segoe UI", 10, "bold"), bg="white", fg="#1E88E5").pack(pady=2)
    tk.Label(stats_frame, textvariable=waiting_var,
             font=("Segoe UI", 9), bg="white", fg="#546E7A").pack(pady=1)
    tk.Label(stats_frame, textvariable=served_var,
             font=("Segoe UI", 9), bg="white", fg="#546E7A").pack(pady=1)

    focus_sep = tk.Frame(box1, bg="#E0E0E0", height=1)
    focus_panel = tk.Frame(box1, bg="#E3F2FD", padx=8, pady=6)

    tk.Label(focus_panel, text="🎯 Focused Ticket",
             font=("Segoe UI", 8, "bold"), bg="#E3F2FD", fg="#1565C0").pack(anchor="w")

    focus_ticket_var = tk.StringVar(value="")
    focus_status_var = tk.StringVar(value="")

    tk.Label(focus_panel, textvariable=focus_ticket_var,
             font=("Segoe UI", 14, "bold"), bg="#E3F2FD", fg="#0D47A1").pack(anchor="w", pady=(2, 0))
    tk.Label(focus_panel, textvariable=focus_status_var,
             font=("Segoe UI", 8), bg="#E3F2FD", fg="#1565C0").pack(anchor="w")

    clear_focus_btn = tk.Button(
        focus_panel, text="✕ Clear Focus",
        font=("Segoe UI", 8, "bold"),
        bg="#90CAF9", fg="#0D47A1", bd=0, padx=6, pady=3, cursor="hand2"
    )
    clear_focus_btn.pack(anchor="e", pady=(4, 0))
    clear_focus_btn.bind("<Enter>", lambda e: clear_focus_btn.config(bg="#64B5F6"))
    clear_focus_btn.bind("<Leave>", lambda e: clear_focus_btn.config(bg="#90CAF9"))

    def _show_focus_panel(ticket_number, status_text):
        focus_ticket_var.set(ticket_number)
        focus_status_var.set(status_text)
        try:
            focus_sep.pack(fill="x", pady=(8, 0))
            focus_panel.pack(fill="x", pady=(4, 0))
        except:
            pass

    def _hide_focus_panel():
        focused_ticket["number"]       = None
        focused_ticket["service_code"] = None
        focus_ticket_var.set("")
        focus_status_var.set("")
        try:
            focus_sep.pack_forget()
            focus_panel.pack_forget()
        except:
            pass

    clear_focus_btn.config(command=_hide_focus_panel)

    # LEFT: Quick Actions
    box2 = card_box(left_frame)
    tk.Label(box2, text="Quick Actions",
             font=("Segoe UI", 13, "bold"), bg="white", fg="#263238").pack(pady=(0, 8))

    btn_container = tk.Frame(box2, bg="white")
    btn_container.pack(fill="x")

    def styled_btn(text, color, hover, command):
        btn = tk.Button(btn_container, text=text, font=("Segoe UI", 9, "bold"),
                        bg=color, fg="white", bd=0, padx=8, pady=6,
                        command=command, cursor="hand2")
        btn.pack(fill="x", pady=3)
        btn.bind("<Enter>", lambda e: btn.config(bg=hover))
        btn.bind("<Leave>", lambda e: btn.config(bg=color))
        return btn

    # LEFT: Queue Display Panel
    box3_shadow = tk.Frame(left_frame, bg="#DADDE1")
    box3_shadow.pack(fill="x", pady=6)
    box3 = tk.Frame(box3_shadow, bg="white", padx=12, pady=10)
    box3.pack(padx=3, pady=3, fill="x")

    tk.Label(box3, text="Queue Display",
             font=("Segoe UI", 13, "bold"), bg="white", fg="#263238").pack(pady=(0, 2))

    tk.Label(box3, text="Click a ticket to focus • Auto-advances on Serve/Skip",
             font=("Segoe UI", 8, "italic"), bg="white", fg="#9E9E9E").pack(pady=(0, 6))

    queue_style = ttk.Style()
    queue_style.configure("Queue.Treeview",        font=("Segoe UI", 8), rowheight=20)
    queue_style.configure("Queue.Treeview.Heading",font=("Segoe UI", 8, "bold"))

    q_tree_frame = tk.Frame(box3, bg="white")
    q_tree_frame.pack(fill="x")

    q_tree = ttk.Treeview(q_tree_frame, columns=("Ticket", "Service"),
                          show="headings", style="Queue.Treeview", height=8)
    q_tree.pack(side="left", fill="x", expand=True)

    q_scroll = ttk.Scrollbar(q_tree_frame, orient="vertical", command=q_tree.yview)
    q_tree.configure(yscrollcommand=q_scroll.set)
    q_scroll.pack(side="right", fill="y")

    q_tree.heading("Ticket",  text="Ticket");  q_tree.column("Ticket",  width=80,  anchor="center")
    q_tree.heading("Service", text="Service"); q_tree.column("Service", width=120, anchor="w")

    q_tree.tag_configure("serving", background="#E3F2FD", font=("Segoe UI", 8, "bold"))
    q_tree.tag_configure("waiting", background="white")

    def load_queue_display():
        def _fetch():
            if not is_active["value"]:
                return
            try:
                r = requests.get(f"{API_BASE_URL}/queue/deploy-order",
                                 timeout=FAST_TIMEOUT)
                if r.status_code == 200:
                    d = r.json()
                    if d.get("success"):
                        parent_frame.after(0, lambda: _apply_queue(d.get("queue", [])))
            except Exception as e:
                print(f"[QUEUE CONSOLE] load_queue_display error: {e}")
        threading.Thread(target=_fetch, daemon=True).start()

    _queue_snapshot = []

    def _apply_queue(rows):
        if not is_active["value"]:
            return
        try:
            if not q_tree.winfo_exists():
                return
            q_tree.delete(*q_tree.get_children())
            _queue_snapshot.clear()
            for entry in rows:
                tag = "serving" if entry["status"] == "Serving" else "waiting"
                q_tree.insert("", "end",
                              values=(entry["ticket_number"], entry["service_name"]),
                              tags=(tag,))
                _queue_snapshot.append({
                    "ticket_number": entry["ticket_number"],
                    "service_name":  entry["service_name"],
                    "status":        entry["status"],
                })
        except Exception as e:
            print(f"[QUEUE CONSOLE] _apply_queue error: {e}")

    def _auto_switch_to_next(after_ticket_number: str):
        if not is_active["value"]:
            return
        if not _queue_snapshot:
            return

        current_idx = None
        for i, entry in enumerate(_queue_snapshot):
            if entry["ticket_number"] == after_ticket_number:
                current_idx = i
                break

        candidate = None
        if current_idx is not None and current_idx + 1 < len(_queue_snapshot):
            candidate = _queue_snapshot[current_idx + 1]
        else:
            for entry in _queue_snapshot:
                if entry["status"] == "Serving":
                    candidate = entry
                    break
            if candidate is None and _queue_snapshot:
                candidate = _queue_snapshot[0]

        if candidate is None:
            return

        next_code = _service_code_from_ticket(candidate["ticket_number"])
        if not next_code:
            return

        matched_value = None
        for v in (service_dropdown["values"] if service_dropdown else []):
            _, vc = _clean_service_str(v)
            if vc == next_code:
                matched_value = v
                break

        if matched_value is None:
            return

        if (focused_ticket["number"] == candidate["ticket_number"]
                and service_var.get() == matched_value):
            return

        service_var.set(matched_value)
        update_service_stats()

        focused_ticket["number"]       = candidate["ticket_number"]
        focused_ticket["service_code"] = next_code
        _show_focus_panel(
            candidate["ticket_number"],
            "Currently Serving" if candidate["status"] == "Serving" else "Waiting in Queue"
        )
        print(f"[QUEUE CONSOLE] Auto-switched to next ticket "
              f"{candidate['ticket_number']!r} (service {next_code!r}).")

    def _on_queue_row_click(event):
        if not is_active["value"]:
            return
        sel = q_tree.selection()
        if not sel:
            return

        row_vals      = q_tree.item(sel[0], "values")
        ticket_number = row_vals[0]
        row_status    = q_tree.item(sel[0], "tags")[0] if q_tree.item(sel[0], "tags") else "waiting"
        clicked_code  = _service_code_from_ticket(ticket_number)

        if not clicked_code:
            print(f"[QUEUE CONSOLE] Could not extract service code from: {ticket_number!r}")
            return

        if not active_services:
            return

        matched_value = None
        for v in (service_dropdown["values"] if service_dropdown else []):
            _, vc = _clean_service_str(v)
            if vc == clicked_code:
                matched_value = v
                break

        if matched_value is None:
            print(f"[QUEUE CONSOLE] Service code {clicked_code!r} not found in dropdown.")
            return

        service_var.set(matched_value)
        update_service_stats()

        focused_ticket["number"]       = ticket_number
        focused_ticket["service_code"] = clicked_code

        status_label = "Currently Serving" if row_status == "serving" else "Waiting in Queue"
        _show_focus_panel(ticket_number, status_label)

        print(f"[QUEUE CONSOLE] Focused on ticket {ticket_number!r} (service {clicked_code!r}).")

    q_tree.bind("<<TreeviewSelect>>", _on_queue_row_click)

    # MIDDLE: Ticket Service Assignment
    middle_box = card_fill(middle_frame)
    tk.Label(middle_box, text="Ticket Service Assignment",
             font=("Segoe UI", 14, "bold"), bg="white", fg="#263238").pack(pady=(0, 10))

    table_container = tk.Frame(middle_box, bg="white")
    table_container.pack(fill="both", expand=True)

    canvas        = tk.Canvas(table_container, bg="white", highlightthickness=0)
    scrollbar_mid = ttk.Scrollbar(table_container, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas, bg="white")
    scrollable_frame.bind("<Configure>",
                          lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.bind("<Configure>",
                lambda e: canvas.itemconfig(canvas_window, width=e.width))
    canvas.configure(yscrollcommand=scrollbar_mid.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar_mid.pack(side="right", fill="y")

    ticket_rows          = {}
    no_tickets_label_ref = {"label": None}

    # RIGHT TOP: Served Tickets (Redo)
    redo_shadow = tk.Frame(right_frame, bg="#DADDE1")
    redo_shadow.pack(fill="x", pady=6)
    redo_box = tk.Frame(redo_shadow, bg="white", padx=12, pady=10)
    redo_box.pack(padx=3, pady=3, fill="x")

    tk.Label(redo_box, text="Served Tickets",
             font=("Segoe UI", 13, "bold"), bg="white", fg="#263238").pack(pady=(0, 2))
    tk.Label(redo_box, text="Select a row then click Redo to re-queue",
             font=("Segoe UI", 8, "italic"), bg="white", fg="#9E9E9E").pack(pady=(0, 6))

    redo_style = ttk.Style()
    redo_style.configure("Redo.Treeview",        font=("Segoe UI", 8), rowheight=22)
    redo_style.configure("Redo.Treeview.Heading",font=("Segoe UI", 8, "bold"))

    redo_tree_frame = tk.Frame(redo_box, bg="white")
    redo_tree_frame.pack(fill="x")

    redo_cols = ("Ticket", "Time")
    redo_tree = ttk.Treeview(redo_tree_frame, columns=redo_cols,
                             show="headings", style="Redo.Treeview", height=6)
    redo_tree.pack(side="left", fill="x", expand=True)

    redo_scroll = ttk.Scrollbar(redo_tree_frame, orient="vertical", command=redo_tree.yview)
    redo_tree.configure(yscrollcommand=redo_scroll.set)
    redo_scroll.pack(side="right", fill="y")

    redo_tree.heading("Ticket", text="Ticket"); redo_tree.column("Ticket", width=110, anchor="center")
    redo_tree.heading("Time",   text="Time");   redo_tree.column("Time",   width=80,  anchor="center")

    redo_btn = tk.Button(
        redo_box, text="  Redo Selected",
        font=("Segoe UI", 9, "bold"),
        bg="#FB8C00", fg="white", bd=0,
        padx=8, pady=5, cursor="hand2"
    )
    redo_btn.pack(fill="x", pady=(6, 0))
    redo_btn.bind("<Enter>", lambda e: redo_btn.config(bg="#EF6C00"))
    redo_btn.bind("<Leave>", lambda e: redo_btn.config(bg="#FB8C00"))

    _redo_ticket_ids = {}

    def load_served_tickets():
        def _fetch():
            if not is_active["value"]:
                return
            try:
                all_tickets = []
                for status in ("Served", "Skipped"):
                    r = requests.get(
                        f"{API_BASE_URL}/tickets/list",
                        params={"status": status, "today_only": "true"},
                        timeout=FAST_TIMEOUT
                    )
                    if r.status_code == 200:
                        d = r.json()
                        if d.get("success"):
                            all_tickets.extend([
                                t for t in d.get("tickets", [])
                                if t.get("queue_type") != "ABTC"
                            ])

                seen = set()
                unique = []
                for t in all_tickets:
                    tid = t.get("ticket_id")
                    if tid not in seen:
                        seen.add(tid)
                        unique.append(t)

                unique.sort(
                    key=lambda t: t.get("updated_at") or t.get("created_at") or "",
                    reverse=True
                )

                parent_frame.after(0, lambda: _apply_served(unique))
            except Exception as e:
                print(f"[QUEUE CONSOLE] load_served_tickets error: {e}")
        threading.Thread(target=_fetch, daemon=True).start()

    def _apply_served(tickets):
        if not is_active["value"]:
            return
        try:
            if not redo_tree.winfo_exists():
                return
            redo_tree.delete(*redo_tree.get_children())
            _redo_ticket_ids.clear()
            for t in tickets:
                full_num = t.get("display_ticket_number") or t.get("ticket_number", "")
                parts = full_num.split("-")
                base_num = (parts[-1] if len(parts) > 1
                            and parts[-1]
                            and parts[-1][0] in ("R", "P", "S")
                            else full_num)
                raw_time = t.get("updated_at") or t.get("created_at") or ""
                time_str = _parse_utc_to_local(raw_time)
                iid = redo_tree.insert("", "end", values=(base_num, time_str))
                _redo_ticket_ids[iid] = {
                    "ticket_id":     t.get("ticket_id"),
                    "ticket_number": full_num,
                    "patient_name":  t.get("patient_name") or "",
                }
        except Exception as e:
            print(f"[QUEUE CONSOLE] _apply_served error: {e}")

    def redo_ticket():
        sel = redo_tree.selection()
        if not sel:
            messagebox.showwarning("No Selection",
                                   "Please click a served ticket row first.",
                                   parent=parent_frame)
            return

        iid  = sel[0]
        info = _redo_ticket_ids.get(iid)
        if not info:
            return

        ticket_id   = info["ticket_id"]
        display_num = info["ticket_number"]
        parts = display_num.split("-")
        show_num = (parts[-1] if len(parts) > 1
                    and parts[-1]
                    and parts[-1][0] in ("R", "P", "S")
                    else display_num)

        if not messagebox.askyesno(
            "Confirm Redo",
            f"Re-queue ticket  {show_num}?\n\n"
            f"It will appear in Ticket Service Assignment again.",
            parent=parent_frame
        ):
            return

        redo_btn.config(state="disabled", text="Processing...")

        def _put():
            try:
                r = requests.put(
                    f"{API_BASE_URL}/tickets/{ticket_id}/update",
                    json={"stage": 3, "status": "Ready for Service",
                          "service_code": None, "assigned_service": None},
                    timeout=REQUEST_TIMEOUT
                )
                if r.status_code == 200 and r.json().get("success"):
                    def _ok():
                        redo_btn.config(state="normal", text="  Redo Selected")
                        load_served_tickets()
                        load_pending_tickets()
                        load_activity()
                        update_service_stats()
                        load_queue_display()
                    parent_frame.after(0, _ok)
                else:
                    def _err():
                        redo_btn.config(state="normal", text="  Redo Selected")
                        messagebox.showerror("Error", "Failed to re-queue ticket.",
                                             parent=parent_frame)
                    parent_frame.after(0, _err)
            except Exception as e:
                def _err(msg=str(e)):
                    try:
                        redo_btn.config(state="normal", text="  Redo Selected")
                    except:
                        pass
                    messagebox.showerror("Error", f"Connection error: {msg}",
                                         parent=parent_frame)
                parent_frame.after(0, _err)

        threading.Thread(target=_put, daemon=True).start()

    redo_btn.config(command=redo_ticket)

    # RIGHT BOTTOM: Activity Log
    activity_box = card_fill(right_frame)
    tk.Label(activity_box, text="Recent Activity",
             font=("Segoe UI", 13, "bold"), bg="white", fg="#263238").pack(pady=(0, 8))

    style = ttk.Style()
    style.configure("Console.Treeview",        font=("Segoe UI", 9), rowheight=24)
    style.configure("Console.Treeview.Heading",font=("Segoe UI", 9, "bold"))

    tree_frame_r = tk.Frame(activity_box, bg="white")
    tree_frame_r.pack(fill="both", expand=True)

    columns = ("Ticket", "Service", "Status", "Time")
    tree = ttk.Treeview(tree_frame_r, columns=columns, show="headings",
                        style="Console.Treeview")
    tree.pack(side="left", fill="both", expand=True)
    tree_scroll = ttk.Scrollbar(tree_frame_r, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=tree_scroll.set)
    tree_scroll.pack(side="right", fill="y")

    tree.heading("Ticket",  text="Ticket");  tree.column("Ticket",  width=65,  anchor="center")
    tree.heading("Service", text="Service"); tree.column("Service", width=100, anchor="center")
    tree.heading("Status",  text="Status");  tree.column("Status",  width=85,  anchor="center")
    tree.heading("Time",    text="Time");    tree.column("Time",    width=65,  anchor="center")

    # DATA HELPERS

    def current_service_code():
        val = service_var.get()
        if not val or not active_services:
            return None
        _, code = _clean_service_str(val)
        return code

    def load_activity():
        def _fetch():
            if not is_active["value"]:
                return
            try:
                today = datetime.now().strftime("%b %d, %Y")
                r = requests.get(f"{API_BASE_URL}/activity/list",
                                 params={"date": today},
                                 timeout=FAST_TIMEOUT)
                if r.status_code == 200:
                    d = r.json()
                    if d.get("success"):
                        parent_frame.after(0, lambda: _apply_activity(d.get("logs", [])))
            except Exception as e:
                print(f"[QUEUE CONSOLE] load_activity error: {e}")
        threading.Thread(target=_fetch, daemon=True).start()

    def _apply_activity(logs):
        if not is_active["value"]:
            return
        try:
            if not tree.winfo_exists():
                return
            tree.delete(*tree.get_children())
            for log in logs:
                try:
                    tree.insert("", "end", values=(
                        log["ticket_number"], log["service_name"],
                        log["status"], log["time"]))
                except:
                    pass
        except:
            pass

    def update_service_stats():
        global last_selected_service_code
        code = current_service_code()
        if not code:
            return
        last_selected_service_code = code

        def _fetch():
            if not is_active["value"]:
                return
            try:
                r2 = requests.get(f"{API_BASE_URL}/queue/service-stats-all",
                                  timeout=FAST_TIMEOUT)
                serving_codes = []
                if r2.status_code == 200:
                    d2 = r2.json()
                    if d2.get("success"):
                        serving_codes = d2.get("serving_codes", [])

                new_values = []
                for name, sc in active_services:
                    suffix = " ●" if sc in serving_codes else ""
                    new_values.append(f"{name} ({sc}){suffix}")

                r = requests.get(f"{API_BASE_URL}/queue/service-stats",
                                 params={"service_code": code},
                                 timeout=FAST_TIMEOUT)
                stats = {}
                if r.status_code == 200:
                    d = r.json()
                    if d.get("success"):
                        stats = d

                def _apply():
                    if not is_active["value"]:
                        return
                    if service_dropdown:
                        try:
                            service_dropdown["values"] = new_values
                            for v in new_values:
                                _, vc = _clean_service_str(v)
                                if vc == code:
                                    service_var.set(v)
                                    break
                        except:
                            pass
                    serving_var.set(f"Serving: {stats.get('serving') or 'None'}")
                    waiting_var.set(f"Waiting: {stats.get('waiting', 0)}")
                    served_var.set(f"Served: {stats.get('served', 0)}")

                parent_frame.after(0, _apply)
            except Exception as e:
                print(f"[QUEUE CONSOLE] update_service_stats error: {e}")

        threading.Thread(target=_fetch, daemon=True).start()

    def load_pending_tickets():
        def _fetch():
            if not is_active["value"]:
                return
            try:
                r = requests.get(
                    f"{API_BASE_URL}/tickets/list",
                    params={"stage": 3, "status": "Ready for Service", "today_only": "true"},
                    timeout=FAST_TIMEOUT
                )
                if r.status_code == 200:
                    d = r.json()
                    if d.get("success"):
                        tickets = [
                            (
                                t.get("display_ticket_number") or t["ticket_number"],
                                t["patient_name"],
                                t.get("queue_type", "Regular"),
                                t["created_at"]
                            )
                            for t in d.get("tickets", [])
                        ]
                        parent_frame.after(0, lambda: _apply_tickets(tickets))
                    else:
                        print(f"[QUEUE CONSOLE] load_pending_tickets not success: {d}")
                else:
                    print(f"[QUEUE CONSOLE] load_pending_tickets HTTP {r.status_code}")
            except Exception as e:
                print(f"[QUEUE CONSOLE] load_pending_tickets error: {e}")
        threading.Thread(target=_fetch, daemon=True).start()

    def _apply_tickets(tickets):
        if not is_active["value"]:
            return

        current_nums = {t[0] for t in tickets}

        for tn in list(ticket_rows.keys()):
            if tn not in current_nums:
                try:
                    ticket_rows[tn].destroy()
                except:
                    pass
                ticket_rows.pop(tn, None)
                ticket_selections.pop(tn, None)

        for tn, pname, qtype, _ in tickets:
            if tn not in ticket_rows:
                _create_ticket_row(tn, pname, qtype)

        if not tickets:
            if no_tickets_label_ref["label"] is None:
                try:
                    no_tickets_label_ref["label"] = tk.Label(
                        scrollable_frame,
                        text="No tickets waiting for service assignment",
                        font=("Segoe UI", 11, "italic"),
                        bg="white", fg="#9E9E9E")
                    no_tickets_label_ref["label"].pack(pady=30)
                except:
                    no_tickets_label_ref["label"] = None
        else:
            if no_tickets_label_ref["label"] is not None:
                try:
                    no_tickets_label_ref["label"].destroy()
                except:
                    pass
                no_tickets_label_ref["label"] = None

    # TICKET ROW BUILDER

    def _create_ticket_row(ticket_number, patient_name, queue_type):
        if not is_active["value"]:
            return

        row_frame = tk.Frame(scrollable_frame, bg="#F0F0F0", relief="solid", bd=1)
        row_frame.pack(fill="x", expand=True, pady=3, padx=2)

        header_f = tk.Frame(row_frame, bg="white")
        header_f.pack(fill="x", padx=2, pady=2)

        info_f = tk.Frame(header_f, bg="white")
        info_f.pack(side="left", padx=8, pady=5)
        tk.Label(info_f, text=ticket_number, font=("Segoe UI", 12, "bold"),
                 bg="white", fg="#000000").pack(anchor="w")
        tk.Label(info_f, text=patient_name or "No Name",
                 font=("Segoe UI", 9), bg="white", fg="#546E7A").pack(anchor="w")
        tk.Label(info_f, text=f"Type: {queue_type}",
                 font=("Segoe UI", 8), bg="white", fg="#9E9E9E").pack(anchor="w")

        action_f = tk.Frame(header_f, bg="white")
        action_f.pack(side="right", padx=8, pady=5)

        add_svc_btn = tk.Button(action_f, text="+ Add Service",
                                font=("Segoe UI", 9, "bold"),
                                bg="#7B1FA2", fg="white", bd=0,
                                padx=8, pady=3, cursor="hand2")
        add_svc_btn.pack(side="left", padx=3)

        send_display_btn = tk.Button(action_f, text="Send to Display",
                                     font=("Segoe UI", 9, "bold"),
                                     bg="#43A047", fg="white", bd=0,
                                     padx=8, pady=3, cursor="hand2")
        send_display_btn.pack(side="left", padx=3)

        services_container = tk.Frame(row_frame, bg="white")
        services_container.pack(fill="x", expand=True, padx=8, pady=(0, 5))

        service_assignments = []

        def add_service_row(row_index):
            if not is_active["value"]:
                return

            asgn = {"status": False, "code": None, "name": None}
            service_assignments.append(asgn)

            service_row = tk.Frame(services_container, bg="white")
            service_row.pack(fill="x", expand=True, pady=2)

            sv_local  = tk.StringVar()
            dd_values = [f"{n} ({c})" for n, c in active_services]
            dropdown_c = tk.Frame(service_row, bg="white")
            dropdown_c.pack(side="left", fill="x", expand=True, padx=5)

            combo = ttk.Combobox(dropdown_c, textvariable=sv_local,
                                 state="readonly", values=dd_values,
                                 font=("Segoe UI", 9))
            combo.pack(side="left", fill="x", expand=True)

            if (ticket_number in ticket_selections
                    and row_index < len(ticket_selections[ticket_number])):
                saved = ticket_selections[ticket_number][row_index]
                if saved:
                    sv_local.set(saved.replace(" *", "").replace("*", "").strip())

            btn_c = tk.Frame(service_row, bg="white")
            btn_c.pack(side="right", padx=5)

            check_btn  = tk.Button(btn_c, text="\u2713", font=("Segoe UI", 10, "bold"),
                                   bg="#1E88E5", fg="white", bd=0, width=4, cursor="hand2")
            undo_btn   = tk.Button(btn_c, text="\u21bb", font=("Segoe UI", 10, "bold"),
                                   bg="#FB8C00", fg="white", bd=0, width=4, cursor="hand2")
            remove_btn = tk.Button(btn_c, text="\u2715", font=("Segoe UI", 10, "bold"),
                                   bg="#E53935", fg="white", bd=0, width=4, cursor="hand2")

            if (ticket_number in ticket_selections
                    and row_index < len(ticket_selections[ticket_number])):
                saved = ticket_selections[ticket_number][row_index]
                if saved:
                    sn, sc = _clean_service_str(saved)
                    if sc:
                        asgn.update({"status": True, "code": sc, "name": sn})
                        combo.config(state="disabled")
                        undo_btn.pack(side="left", padx=2)
                        if row_index > 0:
                            remove_btn.pack(side="left", padx=2)
                    else:
                        check_btn.pack(side="left", padx=2)
                        if row_index > 0:
                            remove_btn.pack(side="left", padx=2)
                else:
                    check_btn.pack(side="left", padx=2)
                    if row_index > 0:
                        remove_btn.pack(side="left", padx=2)
            else:
                check_btn.pack(side="left", padx=2)
                if row_index > 0:
                    remove_btn.pack(side="left", padx=2)

            def assign(a=asgn):
                sel = sv_local.get()
                if not sel:
                    messagebox.showwarning("No Service", "Please select a service",
                                           parent=parent_frame)
                    return
                sn, sc = _clean_service_str(sel)
                if not sc:
                    messagebox.showerror("Error",
                                         f"Could not read service code from: {sel!r}",
                                         parent=parent_frame)
                    return
                a.update({"status": True, "code": sc, "name": sn})
                clean = f"{sn} ({sc})"
                if ticket_number not in ticket_selections:
                    ticket_selections[ticket_number] = []
                while len(ticket_selections[ticket_number]) <= row_index:
                    ticket_selections[ticket_number].append(None)
                ticket_selections[ticket_number][row_index] = clean
                combo.config(state="disabled")
                check_btn.pack_forget()
                undo_btn.pack(side="left", padx=2)
                if row_index > 0:
                    remove_btn.pack(side="left", padx=2)

            def undo(a=asgn):
                combo.config(state="readonly")
                undo_btn.pack_forget()
                remove_btn.pack_forget()
                check_btn.pack(side="left", padx=2)
                if row_index > 0:
                    remove_btn.pack(side="left", padx=2)
                a.update({"status": False, "code": None, "name": None})
                if (ticket_number in ticket_selections
                        and row_index < len(ticket_selections[ticket_number])):
                    ticket_selections[ticket_number][row_index] = None

            def remove(a=asgn):
                idx = next(
                    (i for i, item in enumerate(service_assignments) if item is a),
                    None
                )
                if idx is None:
                    return
                if idx == 0:
                    messagebox.showwarning("Cannot Remove",
                                           "Cannot remove the first service row",
                                           parent=parent_frame)
                    return
                try:
                    service_row.destroy()
                except:
                    pass
                service_assignments.pop(idx)
                if (ticket_number in ticket_selections
                        and idx < len(ticket_selections[ticket_number])):
                    ticket_selections[ticket_number].pop(idx)

            check_btn.config(command=assign)
            undo_btn.config(command=undo)
            remove_btn.config(command=remove)

        if ticket_number in ticket_selections and ticket_selections[ticket_number]:
            for idx in range(len(ticket_selections[ticket_number])):
                add_service_row(idx)
        else:
            add_service_row(0)

        def add_another():
            add_service_row(len(service_assignments))

        def send_to_display():
            confirmed = [a for a in service_assignments
                         if a.get("status") and a.get("code")]

            if not confirmed:
                messagebox.showwarning(
                    "No Confirmed Service",
                    "Please select a service and press ✓ to confirm before sending.",
                    parent=parent_frame
                )
                return

            codes = [a["code"] for a in confirmed]
            send_display_btn.config(state="disabled", text="Sending...")

            def _post():
                try:
                    r = requests.post(
                        f"{API_BASE_URL}/queue/distribute",
                        json={"ticket_number": ticket_number, "service_codes": codes},
                        timeout=REQUEST_TIMEOUT
                    )
                    if r.status_code == 200:
                        d = r.json()
                        if d.get("success"):
                            distributed = d.get("distributed", [])

                            if distributed:
                                def _on_success():
                                    try:
                                        row_frame.destroy()
                                    except:
                                        pass
                                    ticket_rows.pop(ticket_number, None)
                                    ticket_selections.pop(ticket_number, None)
                                    load_activity()
                                    update_service_stats()
                                    load_queue_display()
                                    load_served_tickets()
                                    messagebox.showinfo(
                                        "Success",
                                        f"Ticket {ticket_number} sent to "
                                        f"{len(distributed)} service(s):\n\n"
                                        + "\n".join(distributed),
                                        parent=parent_frame
                                    )
                                parent_frame.after(0, _on_success)

                            else:
                                def _on_zero():
                                    send_display_btn.config(
                                        state="normal", text="Send to Display")
                                    messagebox.showerror(
                                        "Send Failed — Ticket NOT Lost",
                                        f"The server could not distribute ticket "
                                        f"{ticket_number}.\n\n"
                                        f"Codes sent: {codes}\n\n"
                                        f"Possible cause: the service code no longer "
                                        f"exists in OPD Services.\n\n"
                                        f"Please undo your selection, pick a valid "
                                        f"service, confirm, then try again.\n\n"
                                        f"Your ticket is still here — nothing was lost.",
                                        parent=parent_frame
                                    )
                                    # Refresh service
                                    threading.Thread(
                                        target=_init_services, daemon=True).start()
                                parent_frame.after(0, _on_zero)

                        else:
                            def _err(msg=d.get("message", "Failed")):
                                send_display_btn.config(state="normal", text="Send to Display")
                                messagebox.showerror("Error", msg, parent=parent_frame)
                            parent_frame.after(0, _err)
                    else:
                        def _err(sc=r.status_code):
                            send_display_btn.config(state="normal", text="Send to Display")
                            messagebox.showerror("Error", f"Server error: {sc}",
                                                 parent=parent_frame)
                        parent_frame.after(0, _err)

                except Exception as e:
                    def _err(msg=str(e)):
                        try:
                            send_display_btn.config(state="normal", text="Send to Display")
                        except:
                            pass
                        messagebox.showerror("Error", f"Connection error: {msg}",
                                             parent=parent_frame)
                    parent_frame.after(0, _err)

            threading.Thread(target=_post, daemon=True).start()

        add_svc_btn.config(command=add_another)
        send_display_btn.config(command=send_to_display)
        ticket_rows[ticket_number] = row_frame

    # QUICK-ACTION BUTTON COMMANDS

    def call_current():
        if focused_ticket["number"]:
            svc_name = service_var.get().split("(")[0].strip().replace(" *", "").replace(" ●", "")
            speak_ticket_number(focused_ticket["number"], svc_name)
            return

        code = current_service_code()
        if not code:
            messagebox.showwarning("No Service", "Please select a service",
                                   parent=parent_frame)
            return

        def _fetch():
            try:
                r = requests.get(f"{API_BASE_URL}/queue/service-stats",
                                 params={"service_code": code},
                                 timeout=FAST_TIMEOUT)
                if r.status_code == 200:
                    d = r.json()
                    if d.get("success") and d.get("serving"):
                        svc_name = service_var.get().split("(")[0].strip().replace(" *", "")
                        speak_ticket_number(d["serving"], svc_name)
                    else:
                        parent_frame.after(0, lambda: messagebox.showinfo(
                            "No Ticket", "No ticket currently being served",
                            parent=parent_frame))
            except Exception as e:
                print(f"[QUEUE CONSOLE] call_current error: {e}")

        threading.Thread(target=_fetch, daemon=True).start()

    mark_served_state = {"last_click": 0, "cooldown_seconds": 2}

    def mark_served():
        current_time = time.time()
        time_since_last_click = current_time - mark_served_state["last_click"]

        if time_since_last_click < mark_served_state["cooldown_seconds"]:
            remaining = mark_served_state["cooldown_seconds"] - time_since_last_click
            messagebox.showwarning(
                "Please Wait",
                f"Please wait {remaining:.1f} seconds before marking another ticket as served.\n\n"
                f"This prevents accidental double-clicks.",
                parent=parent_frame
            )
            return

        mark_served_state["last_click"] = current_time

        if focused_ticket["number"]:
            tn   = focused_ticket["number"]
            code = focused_ticket["service_code"]

            if not messagebox.askyesno(
                "Confirm Mark Served",
                f"Mark ticket  {tn}  as Served?",
                parent=parent_frame
            ):
                return

            def _post_focused(t=tn, c=code):
                try:
                    r = requests.post(
                        f"{API_BASE_URL}/queue/mark-served-ticket",
                        json={"ticket_number": t, "service_code": c},
                        timeout=REQUEST_TIMEOUT
                    )
                    if r.status_code == 404:
                        r = requests.post(
                            f"{API_BASE_URL}/queue/mark-served",
                            json={"service_code": c},
                            timeout=REQUEST_TIMEOUT
                        )
                    if r.status_code == 200 and r.json().get("success"):
                        def _ok(served_tn=t):
                            load_activity()
                            load_queue_display()
                            load_served_tickets()
                            parent_frame.after(300, lambda: _auto_switch_to_next(served_tn))
                        parent_frame.after(0, _ok)
                    else:
                        def _err(msg=r.json().get("message", "Failed")):
                            messagebox.showerror("Error", msg, parent=parent_frame)
                        parent_frame.after(0, _err)
                except Exception as e:
                    print(f"[QUEUE CONSOLE] mark_served (focused) error: {e}")

            threading.Thread(target=_post_focused, daemon=True).start()
            return

        code = current_service_code()
        if not code:
            messagebox.showwarning("No Service", "Please select a service",
                                   parent=parent_frame)
            return

        def _post():
            try:
                r = requests.post(f"{API_BASE_URL}/queue/mark-served",
                                  json={"service_code": code},
                                  timeout=REQUEST_TIMEOUT)
                if r.status_code == 200:
                    d = r.json()
                    if d.get("success"):
                        served_tn = d.get("served_ticket")
                        def _ok(stn=served_tn):
                            load_activity()
                            load_queue_display()
                            load_served_tickets()
                            if stn:
                                parent_frame.after(300, lambda: _auto_switch_to_next(stn))
                            else:
                                update_service_stats()
                        parent_frame.after(0, _ok)
                    else:
                        parent_frame.after(0, lambda: messagebox.showinfo(
                            "No Ticket", d.get("message", "No ticket to mark"),
                            parent=parent_frame))
                else:
                    parent_frame.after(0, lambda: messagebox.showerror(
                        "Error", f"Server error: {r.status_code}", parent=parent_frame))
            except Exception as e:
                print(f"[QUEUE CONSOLE] mark_served error: {e}")

        threading.Thread(target=_post, daemon=True).start()

    skip_ticket_state = {"last_click": 0, "cooldown_seconds": 2}

    def skip_ticket():
        current_time = time.time()
        time_since_last_click = current_time - skip_ticket_state["last_click"]

        if time_since_last_click < skip_ticket_state["cooldown_seconds"]:
            remaining = skip_ticket_state["cooldown_seconds"] - time_since_last_click
            messagebox.showwarning(
                "Please Wait",
                f"Please wait {remaining:.1f} seconds before skipping another ticket.\n\n"
                f"This prevents accidental double-clicks.",
                parent=parent_frame
            )
            return

        skip_ticket_state["last_click"] = current_time

        if focused_ticket["number"]:
            tn   = focused_ticket["number"]
            code = focused_ticket["service_code"]

            if not messagebox.askyesno(
                "Confirm Skip",
                f"Skip ticket  {tn}?",
                parent=parent_frame
            ):
                return

            def _post_focused(t=tn, c=code):
                try:
                    r = requests.post(
                        f"{API_BASE_URL}/queue/skip-ticket-specific",
                        json={"ticket_number": t, "service_code": c},
                        timeout=REQUEST_TIMEOUT
                    )
                    if r.status_code == 404:
                        r = requests.post(
                            f"{API_BASE_URL}/queue/skip-ticket",
                            json={"service_code": c},
                            timeout=REQUEST_TIMEOUT
                        )
                    if r.status_code == 200 and r.json().get("success"):
                        def _ok(skipped_tn=t):
                            load_activity()
                            load_queue_display()
                            load_served_tickets()
                            parent_frame.after(300, lambda: _auto_switch_to_next(skipped_tn))
                        parent_frame.after(0, _ok)
                    else:
                        def _err(msg=r.json().get("message", "Failed")):
                            messagebox.showerror("Error", msg, parent=parent_frame)
                        parent_frame.after(0, _err)
                except Exception as e:
                    print(f"[QUEUE CONSOLE] skip_ticket (focused) error: {e}")

            threading.Thread(target=_post_focused, daemon=True).start()
            return

        code = current_service_code()
        if not code:
            messagebox.showwarning("No Service", "Please select a service",
                                   parent=parent_frame)
            return

        def _post():
            try:
                r = requests.post(f"{API_BASE_URL}/queue/skip-ticket",
                                  json={"service_code": code},
                                  timeout=REQUEST_TIMEOUT)
                if r.status_code == 200:
                    d = r.json()
                    if d.get("success"):
                        skipped_tn = d.get("skipped_ticket")
                        def _ok(stn=skipped_tn):
                            load_activity()
                            load_queue_display()
                            load_served_tickets()
                            if stn:
                                parent_frame.after(300, lambda: _auto_switch_to_next(stn))
                            else:
                                update_service_stats()
                        parent_frame.after(0, _ok)
                    else:
                        parent_frame.after(0, lambda: messagebox.showinfo(
                            "No Ticket", d.get("message", "No ticket to skip"),
                            parent=parent_frame))
                else:
                    parent_frame.after(0, lambda: messagebox.showerror(
                        "Error", f"Server error: {r.status_code}", parent=parent_frame))
            except Exception as e:
                print(f"[QUEUE CONSOLE] skip_ticket error: {e}")

        threading.Thread(target=_post, daemon=True).start()

    styled_btn("\U0001f4e2 Call",     "#9C27B0", "#7B1FA2", call_current)
    styled_btn("\u2714 Mark Served",  "#43A047", "#2E7D32", mark_served)
    styled_btn("\u23ed Skip",         "#FB8C00", "#EF6C00", skip_ticket)

    refresh_frame = tk.Frame(middle_box, bg="white")
    refresh_frame.pack(fill="x", pady=(10, 0))
    refresh_btn = tk.Button(refresh_frame, text="\U0001f504 Refresh Tickets",
                            font=("Segoe UI", 10, "bold"),
                            bg="#1E88E5", fg="white", bd=0,
                            padx=15, pady=6, cursor="hand2",
                            command=load_pending_tickets)
    refresh_btn.pack()
    refresh_btn.bind("<Enter>", lambda e: refresh_btn.config(bg="#1565C0"))
    refresh_btn.bind("<Leave>", lambda e: refresh_btn.config(bg="#1E88E5"))

    # SERVICE DROPDOWN BOOTSTRAP

    def _init_services():
        try:
            r = requests.get(f"{API_BASE_URL}/services/list",
                             params={"active_only": "true"},
                             timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                d = r.json()
                if d.get("success"):
                    svcs = [(s["service_name"], s["service_code"])
                            for s in d.get("services", [])
                            if s.get("is_active") == 1]
                    parent_frame.after(0, lambda: _build_dropdown(svcs))
                    return
        except Exception as e:
            print(f"[QUEUE CONSOLE] init_services error: {e}")
        parent_frame.after(0, lambda: _build_dropdown([]))

    def _build_dropdown(svcs):
        nonlocal service_dropdown
        if not is_active["value"]:
            return

        active_services.clear()
        active_services.extend(svcs)

        for w in dropdown_placeholder.winfo_children():
            try:
                w.destroy()
            except:
                pass

        if not active_services:
            tk.Label(dropdown_placeholder,
                     text="No active services\n\nPlease add services in\nOPD Services Management",
                     bg="white", fg="#E53935", font=("Segoe UI", 9),
                     justify="center").pack(pady=10)
            return

        tk.Label(dropdown_placeholder, text="Select Service:",
                 bg="white", fg="#546E7A",
                 font=("Segoe UI", 9)).pack(anchor="center", pady=(0, 4))

        dd_values = [f"{n} ({c})" for n, c in active_services]
        service_dropdown = ttk.Combobox(dropdown_placeholder, textvariable=service_var,
                                        state="readonly", values=dd_values,
                                        font=("Segoe UI", 10), justify="center")
        service_dropdown.pack(fill="x")

        if last_selected_service_code:
            for v in dd_values:
                _, vc = _clean_service_str(v)
                if vc == last_selected_service_code:
                    service_var.set(v)
                    break
        if not service_var.get() and dd_values:
            service_var.set(dd_values[0])

        service_dropdown.bind("<<ComboboxSelected>>", lambda e: update_service_stats())

        load_pending_tickets()
        load_activity()
        update_service_stats()
        load_queue_display()
        load_served_tickets()

    def auto_refresh():
        if not is_active["value"]:
            return
        load_pending_tickets()
        load_activity()
        load_queue_display()
        load_served_tickets()
        if active_services:
            update_service_stats()
        safe_after(10_000, auto_refresh)

    threading.Thread(target=_init_services, daemon=True).start()
    safe_after(10_000, auto_refresh)

    print("[QUEUE CONSOLE] Frame loaded (services loading in background)!")