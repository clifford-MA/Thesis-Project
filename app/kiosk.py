import tkinter as tk
from tkinter import ttk, messagebox
import requests
from datetime import datetime
import threading

from config import API_BASE_URL, REQUEST_TIMEOUT, FAST_TIMEOUT

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
    """Return the English word(s) for a number 0–999."""
    if n == 0:
        return "Zero"
    if n < 0:
        return "Negative " + _number_to_words(-n)
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
    """
    Convert a display ticket number to a natural TTS announcement string.

    Examples:
        R001  →  "Regular - Number - One"
        P015  →  "Priority - Number - Fifteen"
        SL003 →  "Special Lane - Number - Three"
        AB001 →  "A B T C - Number - One"
    """
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


def speak_ticket_number_receipt(ticket_number: str):
    """TTS for the receipt Call button. Runs in a daemon thread."""
    def _speak():
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 150)
            engine.setProperty("volume", 1.0)
            for v in engine.getProperty("voices"):
                if "female" in v.name.lower() or "zira" in v.name.lower():
                    engine.setProperty("voice", v.id)
                    break
            announcement = _ticket_to_speech(ticket_number)
            print(f"[KIOSK TTS] Saying: {announcement!r}")
            for _ in range(3):
                engine.say(announcement)
                engine.runAndWait()
            engine.stop()
        except Exception as e:
            print(f"[KIOSK TTS ERROR] {e}")

    threading.Thread(target=_speak, daemon=True).start()

# PRINT HELPERS

def print_ticket(ticket_number, queue_type, patient_name, timestamp):
    lines = _build_receipt_lines(ticket_number, queue_type, patient_name, timestamp)
    try:
        import importlib
        escpos_printer = importlib.import_module("escpos.printer")
        Win32Raw = getattr(escpos_printer, "Win32Raw")
        p = Win32Raw()
        _send_escpos(p, lines, ticket_number)
        return True, "Printed successfully"
    except ImportError:
        pass
    except Exception as e:
        print(f"[PRINT] ESC/POS Win32Raw failed: {e}")
    try:
        import win32print
        printer_name = win32print.GetDefaultPrinter()
        raw = _build_raw_text(lines)
        hPrinter = win32print.OpenPrinter(printer_name)
        try:
            hJob = win32print.StartDocPrinter(hPrinter, 1, ("Queue Ticket", None, "RAW"))
            try:
                win32print.StartPagePrinter(hPrinter)
                win32print.WritePrinter(hPrinter, raw)
                win32print.EndPagePrinter(hPrinter)
            finally:
                win32print.EndDocPrinter(hPrinter)
        finally:
            win32print.ClosePrinter(hPrinter)
        return True, f"Printed to: {printer_name}"
    except ImportError:
        return False, "win32print not installed.\nRun: pip install pywin32"
    except Exception as e:
        return False, f"Print failed: {e}"


def _build_receipt_lines(ticket_number, queue_type, patient_name, timestamp):
    sep = "-" * 32
    lines = [
        ("center", "bold",   "ILOCOS SUR MEDICAL CENTER"),
        ("center", "normal", "Outpatient Department"),
        ("center", "normal", "Queue Management System"),
        ("center", "normal", sep),
        ("center", "normal", "YOUR QUEUE NUMBER"),
        ("center", "big",    ticket_number),
        ("center", "normal", sep),
        ("left",   "normal", f"Queue Type : {queue_type}"),
        ("left",   "normal", f"Date       : {timestamp.strftime('%B %d, %Y')}"),
        ("left",   "normal", f"Time       : {timestamp.strftime('%I:%M:%S %p')}"),
    ]
    if patient_name:
        lines.append(("left", "normal", f"Patient    : {patient_name}"))
    lines += [
        ("center", "normal", sep),
        ("center", "normal", "Please wait for your"),
        ("center", "normal", "number to be called."),
        ("center", "normal", ""),
        ("center", "normal", ""),
        ("center", "normal", ""),
    ]
    return lines


def _send_escpos(p, lines, ticket_number):
    p.set(align="center", bold=True, double_height=False, double_width=False)
    for align, style, text in lines:
        if style == "big":
            p.set(align="center", bold=True, double_height=True, double_width=True)
            p.text(text + "\n")
            p.set(align="center", bold=False, double_height=False, double_width=False)
        elif style == "bold":
            p.set(align=align, bold=True, double_height=False, double_width=False)
            p.text(text + "\n")
            p.set(align=align, bold=False)
        else:
            p.set(align=align, bold=False, double_height=False, double_width=False)
            p.text(text + "\n")
    try:
        p.cut()
    except Exception:
        pass


def _build_raw_text(lines):
    ESC      = b"\x1b"
    RESET    = ESC + b"@"
    BOLD_ON  = b"\x1b" + b"E\x01"
    BOLD_OFF = b"\x1b" + b"E\x00"
    BIG_ON   = b"\x1b" + b"!\x38"
    BIG_OFF  = b"\x1b" + b"!\x00"
    CTR      = b"\x1b" + b"a\x01"
    LEFT     = b"\x1b" + b"a\x00"
    CUT      = b"\x1d" + b"V\x41\x00"

    out = RESET
    for align, style, text in lines:
        out += CTR if align == "center" else LEFT
        if style == "big":
            out += BIG_ON + text.encode("ascii", errors="replace") + b"\n" + BIG_OFF
        elif style == "bold":
            out += BOLD_ON + text.encode("ascii", errors="replace") + b"\n" + BOLD_OFF
        else:
            out += text.encode("ascii", errors="replace") + b"\n"
    out += CUT
    return out

# MODULE-LEVEL PERSISTENT CACHE

_ticket_count_cache: dict = {}
_cache_date: str = ""


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _reset_cache_if_new_day():
    global _cache_date
    today = _today()
    if _cache_date != today:
        _ticket_count_cache.clear()
        _cache_date = today
        print(f"[KIOSK] New day ({today}) — cache reset.")


def _get_cache(queue_type: str):
    _reset_cache_if_new_day()
    return _ticket_count_cache.get(queue_type)


def _set_cache(queue_type: str, next_num: int):
    _reset_cache_if_new_day()
    current = _ticket_count_cache.get(queue_type, 0)
    if next_num > current:
        _ticket_count_cache[queue_type] = next_num
        print(f"[KIOSK] Cache updated → {queue_type}: next={next_num:03d}")
    else:
        print(f"[KIOSK] Cache kept    → {queue_type}: next={current:03d} (ignored {next_num:03d})")


def get_queue_prefix(queue_type: str) -> str:
    prefixes = {
        "Regular":      "R",
        "Priority":     "P",
        "Special Lane": "SL",
        "ABTC":         "AB",
    }
    return prefixes.get(queue_type, "R")


def fetch_next_from_server(queue_type: str, callback):
    prefix = get_queue_prefix(queue_type)

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
                        if t.get("queue_type") != queue_type:
                            continue
                        dtn = t.get("display_ticket_number", "") or ""
                        if "-" in dtn:
                            continue
                        if dtn.startswith(prefix):
                            try:
                                val = int(dtn[len(prefix):])
                                if val > max_num:
                                    max_num = val
                            except (ValueError, IndexError):
                                pass

                    server_next = max_num + 1
                    _set_cache(queue_type, server_next)
                    result = max(server_next, _get_cache(queue_type) or 1)
                    callback(result)
                    return
        except Exception as e:
            print(f"[KIOSK] fetch_next_from_server error ({queue_type}): {e}")

        fallback = _get_cache(queue_type)
        callback(fallback if fallback is not None else 1)

    threading.Thread(target=_fetch, daemon=True).start()

# QUEUE TYPE CONFIG
# NOTE: ABTC is intentionally excluded from Triage/Kiosk.
# ABTC tickets are created in the Admitting module instead.

QUEUE_TYPES = [
    ("Regular",      "Regular",      "#2E7D32", "#1B5E20"),   # Green
    ("Priority",     "Priority",     "#C62828", "#B71C1C"),   # Red
    ("Special Lane", "Special Lane", "#1565C0", "#0D47A1"),   # Blue
]

# COLORS used for indicator dot, receipt header, and ticket number box
_COLORS = {
    "Regular":      "#2E7D32",   # Green
    "Priority":     "#C62828",   # Red
    "Special Lane": "#1565C0",   # Blue
    "ABTC":         "#F9A825",   # Yellow (kept for TTS/receipt use if needed)
}

# ticket number background box in the receipt
_COLORS_LIGHT = {
    "Regular":      "#E8F5E9",   # light green
    "Priority":     "#FFEBEE",   # light red
    "Special Lane": "#E3F2FD",   # light blue
    "ABTC":         "#FFF8E1",   # light yellow (kept for receipt use if needed)
}

# Hover colors for queue type buttons
_HOVER_COLORS = {
    "Regular":      "#1B5E20",
    "Priority":     "#B71C1C",
    "Special Lane": "#0D47A1",
    "ABTC":         "#F57F17",
}

# KIOSK FRAME

def kiosk_frame(parent):
    """STEP 1: TRIAGE — Manual Ticket Creation. ABTC is handled in Admitting."""
    print("[KIOSK] Loading kiosk frame...")

    for widget in parent.winfo_children():
        widget.destroy()
    parent.update_idletasks()

    frame = tk.Frame(parent, bg="#F4F6F8")
    frame.pack(fill="both", expand=True)

    tk.Label(frame, text="Patient Queue Ticket - Triage",
             font=("Segoe UI", 24, "bold"), bg="#F4F6F8", fg="#263238").pack(pady=(35, 5))
    tk.Label(frame, text="Create patient queue ticket",
             font=("Segoe UI", 11), bg="#F4F6F8", fg="#607D8B").pack(pady=(0, 30))

    # TWO-COLUMN LAYOUT
    columns_frame = tk.Frame(frame, bg="#F4F6F8")
    columns_frame.pack()

    right_col = tk.Frame(columns_frame, bg="#F4F6F8")

    # Card outer shell
    shadow = tk.Frame(right_col, bg="#DADDE1")
    shadow.pack()
    card_outer = tk.Frame(shadow, bg="white")
    card_outer.pack(padx=4, pady=4)

    # Colored header band
    create_hdr = tk.Frame(card_outer, bg="#1E88E5", height=56)
    create_hdr.pack(fill="x")
    create_hdr.pack_propagate(False)
    tk.Label(create_hdr, text="✏  CREATE TICKET",
             font=("Segoe UI", 15, "bold"), bg="#1E88E5", fg="white").pack(pady=14)

    # Inner padded area
    card = tk.Frame(card_outer, bg="white", padx=45, pady=28)
    card.pack()

    tk.Label(card, text="TICKET NUMBER", font=("Segoe UI", 12, "bold"),
             bg="white", fg="#37474F").pack(pady=(0, 6))
    ticket_entry = ttk.Entry(card, width=35, justify="center", font=("Segoe UI", 14))
    ticket_entry.pack(pady=(0, 20))

    tk.Label(card, text="INPUT - PATIENT NAME", font=("Segoe UI", 12, "bold"),
             bg="white", fg="#37474F").pack(pady=(0, 6))
    name_entry = ttk.Entry(card, width=35, justify="center")
    name_entry.pack(pady=(0, 20))

    # QUEUE TYPE SELECTION
    # ABTC removed — handled in Admitting module
    tk.Label(card, text="QUEUE TYPE", font=("Segoe UI", 12, "bold"),
             bg="white", fg="#37474F").pack(pady=(0, 8))

    queue_type_var = tk.StringVar(value="Regular")

    # Single row: Regular + Priority + Special Lane
    row1 = tk.Frame(card, bg="white")
    row1.pack(pady=(0, 28))

    radio_style = dict(
        font=("Segoe UI", 11),
        bg="white", fg="#37474F",
        selectcolor="white",
        activebackground="white",
        activeforeground="#1E88E5",
        cursor="hand2",
        indicatoron=True,
    )

    for text, val in [("Regular", "Regular"), ("Priority", "Priority"), ("Special Lane", "Special Lane")]:
        tk.Radiobutton(row1, text=text, variable=queue_type_var, value=val,
                       **radio_style).pack(side="left", padx=20)

    # VISUAL QUEUE TYPE INDICATOR
    indicator_frame = tk.Frame(card, bg="white")
    indicator_frame.pack(pady=(0, 10))
    indicator_lbl = tk.Label(indicator_frame, text="● Regular",
                             font=("Segoe UI", 10, "bold"),
                             bg="white", fg=_COLORS["Regular"])
    indicator_lbl.pack()

    def _on_queue_type_change(*_):
        qt = queue_type_var.get()
        color = _COLORS.get(qt, "#1E88E5")
        indicator_lbl.config(text=f"● {qt}", fg=color)
        _load_ticket_number(qt)

    queue_type_var.trace_add("write", _on_queue_type_change)

    # TICKET NUMBER LOGIC
    _fetch_token = [0]

    def _set_entry(n: int):
        try:
            ticket_entry.delete(0, tk.END)
            ticket_entry.insert(0, f"{n:03d}")
        except Exception:
            pass

    def _load_ticket_number(queue_type: str):
        _fetch_token[0] += 1
        my_token = _fetch_token[0]

        cached = _get_cache(queue_type)
        _set_entry(cached if cached is not None else 1)

        def _on_server_response(n: int):
            if _fetch_token[0] != my_token:
                return
            _set_entry(n)

        fetch_next_from_server(queue_type, _on_server_response)

    _load_ticket_number("Regular")

    # RECEIPT POPUP

    def show_ticket_receipt(ticket_number, queue_type, patient_name, timestamp):
        receipt = tk.Toplevel(parent)
        receipt.title("Queue Ticket")
        receipt.configure(bg="#F4F6F8")
        receipt.resizable(False, False)
        receipt.grab_set()
        receipt.minsize(420, 400)

        shadow_frame = tk.Frame(receipt, bg="#B0BEC5")
        shadow_frame.pack(padx=15, pady=15, fill="both", expand=True)
        ticket_frame = tk.Frame(shadow_frame, bg="white")
        ticket_frame.pack(fill="both", expand=True, padx=3, pady=3)

        hdr_color   = _COLORS.get(queue_type, "#1E88E5")
        light_color = _COLORS_LIGHT.get(queue_type, "#E3F2FD")

        # Header
        hdr = tk.Frame(ticket_frame, bg=hdr_color, width=384, height=100)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="ILOCOS SUR MEDICAL CENTER",
                 font=("Segoe UI", 16, "bold"), bg=hdr_color, fg="white").pack(pady=(15, 2))
        tk.Label(hdr, text="@ Candon City, Ilocos Sur Philippines",
                 font=("Segoe UI", 11), bg=hdr_color, fg="white").pack(pady=(0, 15))

        # Content
        content = tk.Frame(ticket_frame, bg="white")
        content.pack(fill="both", expand=True, padx=25, pady=20)

        tk.Label(content, text="YOUR QUEUE NUMBER",
                 font=("Segoe UI", 11), bg="white", fg="#546E7A").pack(pady=(10, 5))

        # Ticket number box
        nf = tk.Frame(content, bg=light_color, bd=2, relief="solid", height=80)
        nf.pack(fill="x", pady=(0, 20))
        nf.pack_propagate(False)
        tk.Label(nf, text=ticket_number, font=("Segoe UI", 36, "bold"),
                 bg=light_color, fg=hdr_color).place(relx=0.5, rely=0.5, anchor="center")

        tk.Frame(content, bg="#E0E0E0", height=1).pack(fill="x", pady=15)

        def add_detail(label, value, bold=False):
            row = tk.Frame(content, bg="white")
            row.pack(fill="x", pady=6)
            tk.Label(row, text=label, font=("Segoe UI", 10),
                     bg="white", fg="#546E7A", anchor="w", width=15).pack(side="left")
            tk.Label(row, text=value,
                     font=("Segoe UI", 11, "bold") if bold else ("Segoe UI", 11),
                     bg="white", fg="#263238", anchor="w").pack(side="left", fill="x", expand=True)

        add_detail("Queue Type:", queue_type, bold=True)
        add_detail("Date:",       timestamp.strftime("%B %d, %Y"))
        add_detail("Time:",       timestamp.strftime("%I:%M:%S %p"))
        if patient_name:
            add_detail("Patient Name:", patient_name, bold=True)

        tk.Frame(content, bg="#E0E0E0", height=1).pack(fill="x", pady=15)

        # Call button
        call_btn_frame = tk.Frame(ticket_frame, bg="white")
        call_btn_frame.pack(fill="x", padx=25, pady=(0, 25))

        hover_color = dict(zip(
            ["Regular", "Priority", "Special Lane", "ABTC"],
            ["#1B5E20",  "#B71C1C",  "#0D47A1",      "#F57F17"]
        )).get(queue_type, "#1565C0")

        call_btn = tk.Button(
            call_btn_frame,
            text="📢   CALL TICKET",
            font=("Segoe UI", 13, "bold"),
            bg=hdr_color, fg="white", bd=0,
            cursor="hand2", pady=14
        )
        call_btn.pack(fill="x")
        call_btn.bind("<Enter>", lambda e: call_btn.config(bg=hover_color))
        call_btn.bind("<Leave>", lambda e: call_btn.config(bg=hdr_color))

        def _do_call():
            announcement = _ticket_to_speech(ticket_number)
            print(f"[KIOSK RECEIPT] Calling: {announcement!r}")
            call_btn.config(state="disabled", text="Calling...")

            def _after_speak():
                try:
                    call_btn.config(state="normal", text="📢   CALL TICKET")
                except Exception:
                    pass

            def _bg():
                try:
                    import pyttsx3
                    engine = pyttsx3.init()
                    engine.setProperty("rate", 150)
                    engine.setProperty("volume", 1.0)
                    for v in engine.getProperty("voices"):
                        if "female" in v.name.lower() or "zira" in v.name.lower():
                            engine.setProperty("voice", v.id)
                            break
                    for _ in range(3):
                        engine.say(announcement)
                        engine.runAndWait()
                    engine.stop()
                except Exception as e:
                    print(f"[KIOSK TTS ERROR] {e}")
                finally:
                    try:
                        receipt.after(0, _after_speak)
                    except Exception:
                        pass

            threading.Thread(target=_bg, daemon=True).start()

        call_btn.config(command=_do_call)

        receipt.update_idletasks()
        w  = receipt.winfo_reqwidth()
        h  = receipt.winfo_reqheight()
        sw = receipt.winfo_screenwidth()
        sh = receipt.winfo_screenheight()
        receipt.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # CREATE TICKET

    def create_ticket():
        ticket_num   = ticket_entry.get().strip()
        queue_type   = queue_type_var.get()
        patient_name = name_entry.get().strip()

        if not ticket_num:
            messagebox.showerror("Error", "Please enter a ticket number", parent=parent)
            return
        if not ticket_num.isdigit() or len(ticket_num) != 3:
            messagebox.showerror("Error", "Ticket number must be exactly 3 digits (e.g., 001)",
                                 parent=parent)
            return

        btn_create.config(state="disabled", text="Creating...")
        timestamp  = datetime.now()
        manual_num = int(ticket_num)

        def _post():
            try:
                r = requests.post(
                    f"{API_BASE_URL}/tickets/create",
                    json={
                        "patient_name":     patient_name if patient_name else None,
                        "queue_type":       queue_type,
                        "requested_number": manual_num,
                        "force_number":     True,
                    },
                    timeout=REQUEST_TIMEOUT
                )

                if r.status_code == 200:
                    data = r.json()
                    if data.get("success"):
                        created = data.get("ticket_number")
                        print(f"[KIOSK] Server assigned ticket: {created}")

                        prefix = get_queue_prefix(queue_type)
                        try:
                            created_num = int(created[len(prefix):])
                            _set_cache(queue_type, created_num + 1)
                        except (ValueError, IndexError):
                            pass

                        def _on_success():
                            show_ticket_receipt(created, queue_type, patient_name, timestamp)
                            name_entry.delete(0, tk.END)
                            btn_create.config(state="normal", text="CREATE TICKET")
                            _load_ticket_number(queue_type)

                        parent.after(0, _on_success)
                        return

                    else:
                        err = data.get("message", "Failed to create ticket")
                        parent.after(0, lambda: messagebox.showerror("Error", err, parent=parent))

                else:
                    parent.after(0, lambda: messagebox.showerror(
                        "Error", f"Server error: {r.status_code}", parent=parent))

            except requests.exceptions.ConnectionError:
                parent.after(0, lambda: messagebox.showerror(
                    "Connection Error",
                    f"Cannot connect to server at:\n{API_BASE_URL}\n\n"
                    "Please check:\n1. Server is running\n"
                    "2. Both computers on same WiFi",
                    parent=parent))
            except Exception as e:
                parent.after(0, lambda: messagebox.showerror(
                    "Error", f"Failed to create ticket: {e}", parent=parent))

            parent.after(0, lambda: btn_create.config(state="normal", text="CREATE TICKET"))

        threading.Thread(target=_post, daemon=True).start()

    tk.Frame(card, bg="#E3F2FD", height=2).pack(fill="x", pady=(18, 0))

    btn_create = tk.Button(
        card, text="✏   SEND TO ADMITTING",
        font=("Segoe UI", 14, "bold"),
        bg="#1E88E5", fg="white", bd=0,
        padx=35, pady=14, cursor="hand2",
        command=create_ticket
    )
    btn_create.pack(pady=(14, 0))
    btn_create.bind("<Enter>", lambda e: btn_create.config(bg="#1565C0"))
    btn_create.bind("<Leave>", lambda e: btn_create.config(bg="#1E88E5"))

    # LEFT COLUMN
    left_col = tk.Frame(columns_frame, bg="#F4F6F8")
    left_col.pack(side="left", padx=(0, 15), anchor="n")

    # Pack right_col
    right_col.pack(side="left", padx=(15, 0), anchor="n")

    call_shadow = tk.Frame(left_col, bg="#DADDE1")
    call_shadow.pack()
    call_card_outer = tk.Frame(call_shadow, bg="white")
    call_card_outer.pack(padx=4, pady=4)

    # Colored header band
    call_hdr_band = tk.Frame(call_card_outer, bg="#00897B", height=56)
    call_hdr_band.pack(fill="x")
    call_hdr_band.pack_propagate(False)
    tk.Label(call_hdr_band, text="📢  CALL TICKET",
             font=("Segoe UI", 15, "bold"), bg="#00897B", fg="white").pack(pady=14)

    call_card = tk.Frame(call_card_outer, bg="white", padx=45, pady=28)
    call_card.pack()

    tk.Label(call_card, text="Announce a patient's queue number",
             font=("Segoe UI", 10), bg="white", fg="#607D8B").pack(pady=(0, 20))

    # Ticket number input
    tk.Label(call_card, text="TICKET NUMBER", font=("Segoe UI", 12, "bold"),
             bg="white", fg="#37474F").pack(pady=(0, 6))
    call_ticket_entry = ttk.Entry(call_card, width=35, justify="center",
                                   font=("Segoe UI", 14))
    call_ticket_entry.pack(pady=(0, 20))
    call_ticket_entry.insert(0, "001")

    # Queue type selection
    # ABTC removed — handled in Admitting module
    tk.Label(call_card, text="QUEUE TYPE", font=("Segoe UI", 12, "bold"),
             bg="white", fg="#37474F").pack(pady=(0, 8))

    call_queue_type_var = tk.StringVar(value="Regular")

    call_row1 = tk.Frame(call_card, bg="white")
    call_row1.pack(pady=(0, 20))

    call_radio_style = dict(
        font=("Segoe UI", 11),
        bg="white", fg="#37474F",
        selectcolor="white",
        activebackground="white",
        activeforeground="#1E88E5",
        cursor="hand2",
        indicatoron=True,
    )

    # Single row: Regular + Priority + Special Lane (ABTC removed)
    for text, val in [("Regular", "Regular"), ("Priority", "Priority"), ("Special Lane", "Special Lane")]:
        tk.Radiobutton(call_row1, text=text, variable=call_queue_type_var, value=val,
                       **call_radio_style).pack(side="left", padx=20)

    # Indicator dot
    call_indicator_frame = tk.Frame(call_card, bg="white")
    call_indicator_frame.pack(pady=(0, 8))
    call_indicator_lbl = tk.Label(call_indicator_frame, text="● Regular",
                                   font=("Segoe UI", 10, "bold"),
                                   bg="white", fg=_COLORS["Regular"])
    call_indicator_lbl.pack()

    # Preview label
    call_preview_frame = tk.Frame(call_card, bg="#F4F6F8")
    # Not packed
    call_preview_lbl = tk.Label(
        call_preview_frame,
        text='Will announce:\n"Regular - Number - One"',
        font=("Segoe UI", 10, "italic"),
        bg="#F4F6F8", fg="#546E7A",
        justify="center",
        wraplength=260,
    )

    def _update_call_preview(*_):
        """Refresh the indicator dot and the announcement preview label."""
        qt = call_queue_type_var.get()
        color = _COLORS.get(qt, "#1E88E5")
        call_indicator_lbl.config(text=f"● {qt}", fg=color)

        raw_num = call_ticket_entry.get().strip()
        prefix  = get_queue_prefix(qt)
        try:
            num_words = _number_to_words(int(raw_num))
        except ValueError:
            num_words = raw_num

        try:
            padded = f"{int(raw_num):03d}"
        except ValueError:
            padded = raw_num
        full_ticket = f"{prefix}{padded}"
        announcement = _ticket_to_speech(full_ticket)
        call_preview_lbl.config(text=f'Will announce:\n"{announcement}"')

    call_queue_type_var.trace_add("write", _update_call_preview)
    call_ticket_entry.bind("<KeyRelease>", _update_call_preview)

    # CALL TICKET button
    tk.Frame(call_card, bg="#E0F2F1", height=2).pack(fill="x", pady=(18, 0))

    btn_call = tk.Button(
        call_card,
        text="📢   CALL TICKET",
        font=("Segoe UI", 14, "bold"),
        bg="#00897B", fg="white", bd=0,
        padx=35, pady=14, cursor="hand2",
    )
    btn_call.pack(pady=(14, 0))
    btn_call.bind("<Enter>", lambda e: btn_call.config(bg="#00695C"))
    btn_call.bind("<Leave>", lambda e: btn_call.config(bg="#00897B"))

    # Status label
    call_status_lbl = tk.Label(
        call_card, text="",
        font=("Segoe UI", 10), bg="white", fg="#388E3C"
    )
    call_status_lbl.pack(pady=(10, 0))

    def _do_call_only():
        raw_num    = call_ticket_entry.get().strip()
        queue_type = call_queue_type_var.get()

        if not raw_num:
            messagebox.showerror("Error", "Please enter a ticket number", parent=parent)
            return
        if not raw_num.isdigit() or len(raw_num) != 3:
            messagebox.showerror(
                "Error", "Ticket number must be exactly 3 digits (e.g., 001)",
                parent=parent
            )
            return

        prefix      = get_queue_prefix(queue_type)
        full_ticket = f"{prefix}{raw_num}"
        announcement = _ticket_to_speech(full_ticket)

        print(f"[KIOSK CALL] Announcing: {announcement!r}")
        btn_call.config(state="disabled", text="Calling...")
        call_status_lbl.config(text="")

        def _after_speak():
            try:
                btn_call.config(state="normal", text="📢   CALL TICKET")
                call_status_lbl.config(
                    text=f"✔  Last called: {full_ticket}",
                    fg="#388E3C"
                )
            except Exception:
                pass

        def _bg():
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.setProperty("rate", 150)
                engine.setProperty("volume", 1.0)
                for v in engine.getProperty("voices"):
                    if "female" in v.name.lower() or "zira" in v.name.lower():
                        engine.setProperty("voice", v.id)
                        break
                for _ in range(3):
                    engine.say(announcement)
                    engine.runAndWait()
                engine.stop()
            except Exception as e:
                print(f"[KIOSK CALL TTS ERROR] {e}")
            finally:
                try:
                    parent.after(0, _after_speak)
                except Exception:
                    pass

        threading.Thread(target=_bg, daemon=True).start()

    btn_call.config(command=_do_call_only)

    _update_call_preview()

    print("[KIOSK] Frame loaded successfully!")