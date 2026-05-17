import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
import calendar
import threading
import requests
import os
import tempfile

try:
    from tkcalendar import DateEntry
    HAS_DATENTRY = True
except ImportError:
    HAS_DATENTRY = False

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    import matplotlib.gridspec as gridspec
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

from config import API_BASE_URL, REQUEST_TIMEOUT, FAST_TIMEOUT

#  API HELPERS

def _api_get(path, params=None, timeout=FAST_TIMEOUT):
    try:
        r = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=timeout)
        if r.status_code == 200:
            d = r.json()
            if d.get("success"):
                return d
    except Exception as e:
        print(f"[DASHBOARD] GET {path} -> {e}")
    return None


def _api_post(path, payload, timeout=REQUEST_TIMEOUT):
    try:
        r = requests.post(f"{API_BASE_URL}{path}", json=payload, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"[DASHBOARD] POST {path} -> {e}")
    return None

#  OPEN DASHBOARD
def open_dashboard(full_name):

    dash = tk.Tk()
    dash.title("ISMC OPD Queue Management System")
    dash.state("zoomed")
    dash.configure(bg="#F4F6F8")

    def open_display_screen():
        from display_screen import open_display_screen_window
        open_display_screen_window(dash)

    def confirm_logout():
        popup = tk.Toplevel(dash)
        popup.title("Confirm Logout")
        popup.geometry("320x160")
        popup.configure(bg="#F4F6F8")
        popup.resizable(False, False)
        popup.grab_set()
        popup.update_idletasks()
        px = (popup.winfo_screenwidth()  // 2) - 160
        py = (popup.winfo_screenheight() // 2) - 80
        popup.geometry(f"320x160+{px}+{py}")
        tk.Label(popup, text="Are you sure you want to logout?",
                 font=("Segoe UI", 12, "bold"), bg="#F4F6F8").pack(pady=25)

        def _do_logout():
            popup.destroy()
            dash.destroy()
            _open_login()

        def _btn(parent, text, bg, cmd):
            h = "#388E3C" if bg == "#43A047" else "#D32F2F"
            b = tk.Button(parent, text=text, font=("Segoe UI", 11, "bold"),
                          bg=bg, fg="white", bd=2, relief="ridge",
                          cursor="hand2", padx=10, pady=8, command=cmd)
            b.pack(side="left", fill="x", expand=True, padx=5)
            b.bind("<Enter>", lambda e: b.config(bg=h))
            b.bind("<Leave>", lambda e: b.config(bg=bg))

        bf = tk.Frame(popup, bg="#F4F6F8")
        bf.pack(pady=10, fill="x", padx=30)
        _btn(bf, "Yes", "#43A047", _do_logout)
        _btn(bf, "No",  "#E53935", popup.destroy)

    # Header
    header = tk.Frame(dash, bg="#1E88E5", height=80)
    header.pack(fill="x")
    header.pack_propagate(False)

    logo_c = tk.Frame(header, bg="#1E88E5")
    logo_c.pack(side="left", padx=15)
    if HAS_PIL:
        try:
            img   = Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ismc_logo.png")).resize((50, 50), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            ll    = tk.Label(logo_c, image=photo, bg="#1E88E5")
            ll.image = photo
            ll.pack(side="left", padx=(0, 12))
        except Exception:
            tk.Label(logo_c, text="ISMC", font=("Segoe UI", 12, "bold"),
                     bg="#1E88E5", fg="white", width=5).pack(side="left", padx=(0, 12))
    else:
        tk.Label(logo_c, text="ISMC", font=("Segoe UI", 12, "bold"),
                 bg="#1E88E5", fg="white", width=5).pack(side="left", padx=(0, 12))

    lh = tk.Frame(header, bg="#1E88E5")
    lh.pack(side="left")
    tk.Label(lh, text="OPD Queue Management System",
             font=("Segoe UI", 15, "bold"), bg="#1E88E5", fg="white").pack(anchor="w")
    tk.Label(lh, text=f"Welcome, {full_name}",
             font=("Segoe UI", 11), bg="#1E88E5", fg="white").pack(anchor="w", pady=(3, 0))

    content_frame = tk.Frame(dash, bg="#F4F6F8")
    content_frame.pack(fill="both", expand=True)

    nav_group = tk.Frame(header, bg="#1E88E5")
    nav_group.place(relx=0.5, rely=0.5, anchor="center")
    nav_btns = {}
    PAGES = ["Dashboard", "Triage", "Admitting",
             "Queue Console", "Display Screen", "OPD Services"]

    def nav_click(page):
        for b in nav_btns.values():
            b.config(bg="#1E88E5", fg="white", font=("Segoe UI", 10))
        if page in nav_btns:
            nav_btns[page].config(bg="#1565C0", font=("Segoe UI", 10, "bold"))
        for w in content_frame.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass
        content_frame.update_idletasks()
        dash.after(10, lambda: _load(page))

    dash._nav_click = nav_click

    def _load(page):
        try:
            if page == "Dashboard":
                _build_dashboard(content_frame, nav_click)
            elif page == "Triage":
                from kiosk import kiosk_frame
                kiosk_frame(content_frame)
            elif page == "Admitting":
                from admitting import admitting_frame
                admitting_frame(content_frame)
            elif page == "Queue Console":
                from queue_console import queue_console_frame
                queue_console_frame(content_frame)
            elif page == "Display Screen":
                from viewing_screen import viewing_screen_frame
                viewing_screen_frame(content_frame)
            elif page == "OPD Services":
                from opd_services import load_opd_services
                load_opd_services(content_frame)

        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to load {page}:\n{e}")

    for p in PAGES:
        b = tk.Button(nav_group, text=p, bg="#1E88E5", fg="white", bd=0,
                      font=("Segoe UI", 10), padx=12, pady=6,
                      activebackground="#1565C0", cursor="hand2",
                      command=lambda x=p: nav_click(x))
        b.pack(side="left", padx=4)
        nav_btns[p] = b
    nav_btns["Dashboard"].config(bg="#1565C0", font=("Segoe UI", 10, "bold"))

    rh = tk.Frame(header, bg="#1E88E5")
    rh.pack(side="right", padx=20)

    db_btn = tk.Button(rh, text="Display Screen", bg="#FF6F00", fg="white",
                       font=("Segoe UI", 10, "bold"), bd=0, relief="flat",
                       padx=15, pady=6, cursor="hand2", command=open_display_screen)
    db_btn.pack(side="left", padx=(0, 10), pady=20)
    db_btn.bind("<Enter>", lambda e: db_btn.config(bg="#E65100"))
    db_btn.bind("<Leave>", lambda e: db_btn.config(bg="#FF6F00"))

    lo_btn = tk.Button(rh, text="Logout", bg="#D32F2F", fg="white",
                       font=("Segoe UI", 10, "bold"), bd=0, relief="flat",
                       padx=18, pady=6, cursor="hand2", command=confirm_logout)
    lo_btn.pack(side="left", pady=20)
    lo_btn.bind("<Enter>", lambda e: lo_btn.config(bg="#B71C1C"))
    lo_btn.bind("<Leave>", lambda e: lo_btn.config(bg="#D32F2F"))

    nav_click("Dashboard")
    dash.mainloop()

#  RE-OPEN LOGIN

def _open_login():
    import subprocess
    import sys
    subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "login.py")])

#  DASHBOARD PAGE

def _build_dashboard(parent, nav_click):
    is_active = {"v": True}
    _aids     = []

    def safe_after(ms, fn):
        if not is_active["v"]:
            return
        try:
            aid = parent.after(ms, fn)
            _aids.append(aid)
        except Exception:
            pass

    def _cleanup(e=None):
        if e and e.widget is not parent:
            return
        is_active["v"] = False
        for a in _aids:
            try:
                parent.after_cancel(a)
            except Exception:
                pass

    parent.bind("<Destroy>", _cleanup)

    today = datetime.now()

    outer = tk.Frame(parent, bg="#F4F6F8")
    outer.pack(fill="both", expand=True)

    _cv  = tk.Canvas(outer, bg="#F4F6F8", highlightthickness=0)
    _vsb = ttk.Scrollbar(outer, orient="vertical", command=_cv.yview)
    _sf  = tk.Frame(_cv, bg="#F4F6F8")

    _sf.bind("<Configure>", lambda e: _cv.configure(scrollregion=_cv.bbox("all")))
    _win = _cv.create_window((0, 0), window=_sf, anchor="nw")
    _cv.bind("<Configure>", lambda e: _cv.itemconfig(_win, width=e.width))
    _cv.configure(yscrollcommand=_vsb.set)
    _cv.pack(side="left", fill="both", expand=True)
    _vsb.pack(side="right", fill="y")

    def _wheel(e):
        _cv.yview_scroll(int(-1 * (e.delta / 120)), "units")
    _cv.bind_all("<MouseWheel>", _wheel)

    sel_date = tk.StringVar(value=today.strftime("%b %d, %Y"))

    _card(_sf, lambda f: _build_announcement_block(f, parent, is_active))

    m_outer = tk.Frame(_sf, bg="#F4F6F8")
    m_outer.pack(fill="x", padx=15, pady=(0, 8))
    for i in range(4):
        m_outer.columnconfigure(i, weight=1, uniform="mc")

    mv = {
        "total":   tk.StringVar(value="--"),
        "served":  tk.StringVar(value="--"),
        "waiting": tk.StringVar(value="--"),
        "month":   tk.StringVar(value="--"),
        "msub":    tk.StringVar(value="vs last month"),
    }

    for col, (title, key, color) in enumerate([
        ("Total Patients Today",  "total",   "#1E88E5"),
        ("Served Today",          "served",  "#43A047"),
        ("Currently Waiting",     "waiting", "#FB8C00"),
        ("This Month (Served)",   "month",   "#7B1FA2"),
    ]):
        cf = tk.Frame(m_outer, bg="white", relief="solid", bd=1)
        cf.grid(row=0, column=col, sticky="nsew", padx=5, pady=5)
        ci = tk.Frame(cf, bg="white")
        ci.pack(fill="both", expand=True, padx=12, pady=14)
        tk.Label(ci, text=title, font=("Segoe UI", 10),
                 bg="white", fg="#546E7A").pack()
        tk.Label(ci, textvariable=mv[key],
                 font=("Segoe UI", 28, "bold"), bg="white", fg=color).pack(pady=(4, 0))
        if key == "month":
            tk.Label(ci, textvariable=mv["msub"],
                     font=("Segoe UI", 8), bg="white", fg="#78909C").pack()

    def _fetch_metrics():
        stats  = _api_get("/stats/today")
        total  = stats.get("total",   0) if stats else 0
        served = stats.get("served",  0) if stats else 0
        wait   = stats.get("waiting", 0) if stats else 0

        now = datetime.now()
        cs  = now.replace(day=1).strftime("%Y-%m-%d")
        ld  = now.replace(day=1) - timedelta(days=1)
        ls  = ld.replace(day=1).strftime("%Y-%m-%d")
        le  = now.replace(day=1).strftime("%Y-%m-%d")

        d     = _api_get("/tickets/list", {"today_only": "false"})
        all_t = d.get("tickets", []) if d else []
        cur_m = sum(1 for t in all_t
                    if t.get("status") == "Served"
                    and t.get("created_at", "") >= cs)
        prv_m = sum(1 for t in all_t
                    if t.get("status") == "Served"
                    and ls <= t.get("created_at", "") < le)

        if prv_m > 0:
            pct   = (cur_m - prv_m) / prv_m * 100
            arrow = "up" if pct >= 0 else "dn"
            sub   = f"{'(+)' if pct>=0 else '(-)'} {abs(pct):.1f}% vs last month"
        else:
            sub = "No prior month data"

        def _apply():
            mv["total"].set(str(total))
            mv["served"].set(str(served))
            mv["waiting"].set(str(wait))
            mv["month"].set(str(cur_m))
            mv["msub"].set(sub)

        if is_active["v"]:
            parent.after(0, _apply)

    two_col = tk.Frame(_sf, bg="#F4F6F8")
    two_col.pack(fill="both", expand=True, padx=15, pady=(0, 15))
    two_col.columnconfigure(0, weight=6, minsize=420)
    two_col.columnconfigure(1, weight=4, minsize=340)
    two_col.rowconfigure(0, weight=1)

    left_col  = tk.Frame(two_col, bg="#F4F6F8")
    left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
    right_col = tk.Frame(two_col, bg="#F4F6F8")
    right_col.grid(row=0, column=1, sticky="nsew")

    cal_c = _white_card(left_col, pady_bottom=8)
    cal_i = tk.Frame(cal_c, bg="white")
    cal_i.pack(fill="x", padx=14, pady=12)

    dp_row_outer = tk.Frame(cal_i, bg="white")
    dp_row_outer.pack(fill="x", pady=(0, 6))
    dp_row = tk.Frame(dp_row_outer, bg="white")
    dp_row.pack(anchor="center")

    tk.Label(dp_row, text="  Select Date:", font=("Segoe UI", 11, "bold"),
             bg="white", fg="#263238").pack(side="left", padx=(0, 10))

    if HAS_DATENTRY:
        dp = DateEntry(dp_row, width=16, background="#1E88E5", foreground="white",
                       borderwidth=2, font=("Segoe UI", 10),
                       date_pattern="mm/dd/yyyy",
                       year=today.year, month=today.month, day=today.day)
        dp.pack(side="left", padx=4)
    else:
        dp = None
        tk.Label(dp_row, textvariable=sel_date,
                 font=("Segoe UI", 10, "bold"), bg="white",
                 fg="#1E88E5").pack(side="left")

    def _go_today():
        sel_date.set(today.strftime("%b %d, %Y"))
        if dp:
            dp.set_date(today)
        _refresh_cal()
        _on_date_change()

    tk.Button(dp_row, text="Today", bg="#E3F2FD", fg="#1E88E5", bd=0,
              font=("Segoe UI", 9, "bold"), padx=14, pady=5,
              cursor="hand2", command=_go_today).pack(side="left", padx=10)

    if dp:
        def _dp_pick(e=None):
            d = dp.get_date()
            sel_date.set(d.strftime("%b %d, %Y"))
            _refresh_cal()
            _on_date_change()
        dp.bind("<<DateEntrySelected>>", _dp_pick)

    cal_grid = tk.Frame(cal_i, bg="white")
    cal_grid.pack(pady=(8, 4))
    for idx, dn in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        tk.Label(cal_grid, text=dn, font=("Segoe UI", 9, "bold"),
                 bg="white", fg="#546E7A", width=5).grid(row=0, column=idx, padx=1, pady=2)

    _act_dates = {"s": set()}

    def _preload_act_dates():
        d = _api_get("/activity/list")
        dates = set()
        if d:
            for lg in d.get("logs", []):
                raw = lg.get("date", "")
                try:
                    dates.add(datetime.strptime(raw, "%b %d, %Y").date())
                except ValueError:
                    pass
        _act_dates["s"] = dates
        if is_active["v"]:
            parent.after(0, _refresh_cal)

    def _refresh_cal():
        if not is_active["v"]:
            return
        for w in cal_grid.grid_slaves():
            try:
                if int(w.grid_info()["row"]) > 0:
                    w.destroy()
            except Exception:
                pass
        try:
            sel = datetime.strptime(sel_date.get(), "%b %d, %Y")
        except ValueError:
            sel = today

        for r, week in enumerate(calendar.Calendar(0).monthdayscalendar(sel.year, sel.month), 1):
            for c, day in enumerate(week):
                if day == 0:
                    tk.Label(cal_grid, text="", width=5, bg="white").grid(row=r, column=c)
                    continue
                d_obj   = datetime(sel.year, sel.month, day)
                d_str   = d_obj.strftime("%b %d, %Y")
                has_act = d_obj.date() in _act_dates["s"]
                is_sel  = d_str == sel_date.get()
                is_tod  = d_obj.date() == today.date()

                if is_sel:
                    bg, fg, fw = "#1E88E5", "white", "bold"
                elif is_tod:
                    bg, fg, fw = "#E3F2FD", "#1E88E5", "bold"
                elif has_act:
                    bg, fg, fw = "#FFF9C4", "#263238", "normal"
                else:
                    bg, fg, fw = "white", "#546E7A", "normal"

                b = tk.Button(cal_grid, text=str(day), width=5,
                              bg=bg, fg=fg, font=("Segoe UI", 9, fw),
                              bd=1, relief="solid", cursor="hand2",
                              command=lambda ds=d_str, do=d_obj: _pick_cal(ds, do))
                b.grid(row=r, column=c, padx=1, pady=1)

    def _pick_cal(ds, do):
        sel_date.set(ds)
        if dp:
            dp.set_date(do)
        _refresh_cal()
        _on_date_change()

    leg = tk.Frame(cal_i, bg="white")
    leg.pack(pady=(6, 0))
    for ltxt, lbg, lfg in [("Today", "#E3F2FD", "#1E88E5"),
                             ("Selected", "#1E88E5", "white"),
                             ("Has Activity", "#FFF9C4", "#263238")]:
        it = tk.Frame(leg, bg="white")
        it.pack(side="left", padx=8)
        tk.Label(it, text="  ", bg=lbg, fg=lfg, bd=1, relief="solid",
                 width=2, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 3))
        tk.Label(it, text=ltxt, font=("Segoe UI", 8),
                 bg="white", fg="#546E7A").pack(side="left")

    ds_c = _white_card(left_col, pady_bottom=8)
    ds_i = tk.Frame(ds_c, bg="white")
    ds_i.pack(fill="x", padx=14, pady=12)
    tk.Label(ds_i, text="Daily Statistics",
             font=("Segoe UI", 13, "bold"), bg="white", fg="#263238").pack(pady=(0, 8))

    ds_grid = tk.Frame(ds_i, bg="white")
    ds_grid.pack(fill="x")
    for i in range(4):
        ds_grid.columnconfigure(i, weight=1, uniform="ds")

    dsv = {
        "Total":   tk.StringVar(value="0"),
        "Served":  tk.StringVar(value="0"),
        "Waiting": tk.StringVar(value="0"),
        "Skipped": tk.StringVar(value="0"),
    }
    for idx, (lbl, color) in enumerate([("Total",   "#1E88E5"),
                                         ("Served",  "#43A047"),
                                         ("Waiting", "#FB8C00"),
                                         ("Skipped", "#E53935")]):
        f = tk.Frame(ds_grid, bg="white")
        f.grid(row=0, column=idx, sticky="nsew", padx=5, pady=3)
        tk.Label(f, text=lbl, font=("Segoe UI", 9),
                 bg="white", fg="#546E7A").pack()
        tk.Label(f, textvariable=dsv[lbl], font=("Segoe UI", 20, "bold"),
                 bg="white", fg=color).pack()

    def _fetch_daily_stats():
        try:
            dt  = datetime.strptime(sel_date.get(), "%b %d, %Y")
            dbs = dt.strftime("%Y-%m-%d")
        except ValueError:
            return
        d = _api_get("/tickets/list", {"today_only": "false"})
        if not d:
            return
        tickets = [t for t in d.get("tickets", [])
                   if t.get("created_at", "").startswith(dbs)]
        counts = {"Total": len(tickets), "Served": 0, "Waiting": 0, "Skipped": 0}
        for t in tickets:
            s = t.get("status", "")
            if s in counts:
                counts[s] += 1

        def _apply():
            for k in dsv:
                dsv[k].set(str(counts.get(k, 0)))

        if is_active["v"]:
            parent.after(0, _apply)

    tr_c = _white_card(left_col, pady_bottom=8)
    tr_i = tk.Frame(tr_c, bg="white")
    tr_i.pack(fill="both", expand=True, padx=14, pady=12)
    tk.Label(tr_i, text="7-Day Patient Trend (Served)",
             font=("Segoe UI", 13, "bold"), bg="white", fg="#263238").pack(pady=(0, 6))

    trend_cv = tk.Canvas(tr_i, bg="white", height=200, highlightthickness=0)
    trend_cv.pack(fill="x", expand=True)
    _trend = {"data": []}

    def _draw_trend(canvas, data):
        canvas.delete("all")
        canvas.update_idletasks()
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        if cw < 20 or ch < 20:
            return
        if not data or all(v == 0 for _, v in data):
            canvas.create_text(cw // 2, ch // 2,
                               text="No served patients in this period",
                               font=("Segoe UI", 10), fill="#9E9E9E")
            return
        pad   = 42
        max_v = max(v for _, v in data) or 1
        for i in range(5):
            y = pad + i * (ch - 2 * pad) / 4
            canvas.create_line(pad, y, cw - pad, y, fill="#F0F0F0", dash=(3, 3))
            canvas.create_text(pad - 6, y, text=str(int(max_v - max_v * i / 4)),
                               font=("Segoe UI", 7), fill="#9E9E9E", anchor="e")
        step = (cw - 2 * pad) / (len(data) - 1) if len(data) > 1 else 0
        pts  = [(pad + i * step, ch - pad - (v / max_v) * (ch - 2 * pad))
                for i, (_, v) in enumerate(data)]
        if len(pts) > 1:
            canvas.create_polygon(
                [(pad, ch - pad)] + pts + [(cw - pad, ch - pad)],
                fill="#BBDEFB", outline="")
        for i in range(len(pts) - 1):
            canvas.create_line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1],
                               fill="#1E88E5", width=2, smooth=True)
        for (date, cnt), (x, y) in zip(data, pts):
            canvas.create_oval(x - 4, y - 4, x + 4, y + 4,
                               fill="#1E88E5", outline="#0D47A1", width=1)
            try:
                dl = datetime.strptime(date, "%Y-%m-%d").strftime("%m/%d")
            except ValueError:
                dl = date[-5:]
            canvas.create_text(x, ch - pad + 14, text=dl,
                               font=("Segoe UI", 7), fill="#546E7A")
            if cnt > 0:
                canvas.create_text(x, y - 11, text=str(cnt),
                                   font=("Segoe UI", 7, "bold"), fill="#1565C0")

    def _fetch_trend():
        d = _api_get("/tickets/list", {"today_only": "false"})
        if not d:
            _trend["data"] = [(today.strftime("%Y-%m-%d"), 0)]
            return
        tickets = d.get("tickets", [])
        result  = []
        for i in range(6, -1, -1):
            dt  = today - timedelta(days=i)
            ds  = dt.strftime("%Y-%m-%d")
            cnt = sum(1 for t in tickets
                      if t.get("status") == "Served"
                      and t.get("created_at", "").startswith(ds))
            result.append((ds, cnt))
        _trend["data"] = result
        if is_active["v"]:
            parent.after(0, lambda: _draw_trend(trend_cv, result))

    trend_cv.bind("<Configure>", lambda e: _draw_trend(trend_cv, _trend["data"]))

    # Service Distribution
    sd_c = _white_card(left_col, pady_bottom=0)
    sd_i = tk.Frame(sd_c, bg="white")
    sd_i.pack(fill="both", expand=True, padx=14, pady=12)
    tk.Label(sd_i, text="Service Distribution (Selected Date)",
             font=("Segoe UI", 13, "bold"), bg="white", fg="#263238").pack(pady=(0, 6))

    svc_scroll_frame = tk.Frame(sd_i, bg="white")
    svc_scroll_frame.pack(fill="x", expand=True)

    svc_cv  = tk.Canvas(svc_scroll_frame, bg="white", height=220, highlightthickness=0)
    svc_vsb = ttk.Scrollbar(svc_scroll_frame, orient="vertical", command=svc_cv.yview)
    svc_cv.configure(yscrollcommand=svc_vsb.set)
    svc_cv.pack(side="left", fill="x", expand=True)

    _svc = {"data": []}

    _SVC_BAR_HT  = 28
    _SVC_BAR_GAP = 8
    _SVC_PAD_TOP = 18
    _SVC_PAD_BOT = 12

    def _draw_svc(canvas, data):
        canvas.delete("all")
        canvas.update_idletasks()
        cw = canvas.winfo_width()
        if cw < 20:
            return
        if not data:
            canvas.config(height=80)
            svc_vsb.pack_forget()
            canvas.configure(scrollregion=(0, 0, cw, 80))
            canvas.create_text(cw // 2, 40,
                               text="No service data for selected date",
                               font=("Segoe UI", 10), fill="#9E9E9E")
            return

        total_h   = (_SVC_PAD_TOP + len(data) * (_SVC_BAR_HT + _SVC_BAR_GAP) + _SVC_PAD_BOT)
        visible_h = min(total_h, 260)
        canvas.config(height=visible_h)
        canvas.configure(scrollregion=(0, 0, cw, total_h))

        if total_h > visible_h:
            svc_vsb.pack(side="right", fill="y")
        else:
            svc_vsb.pack_forget()

        def _svc_wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind("<MouseWheel>", _svc_wheel)

        pad_left = 40
        max_v    = max(d[2] for d in data) or 1
        fb       = ["#1E88E5", "#43A047", "#FB8C00", "#E53935",
                    "#7B1FA2", "#00ACC1", "#FDD835", "#5E35B1"]

        for i, (name, color, cnt) in enumerate(data):
            y     = _SVC_PAD_TOP + i * (_SVC_BAR_HT + _SVC_BAR_GAP)
            avail = cw - pad_left - 160
            bw    = max(2, int((cnt / max_v) * avail))
            bc    = color or fb[i % len(fb)]
            canvas.create_rectangle(pad_left + 130, y,
                                    pad_left + 130 + bw, y + _SVC_BAR_HT,
                                    fill=bc, outline=bc)
            sn = (name[:14] + "...") if len(name) > 14 else name
            canvas.create_text(pad_left + 125, y + _SVC_BAR_HT / 2,
                               text=sn, anchor="e",
                               font=("Segoe UI", 8), fill="#263238")
            canvas.create_text(pad_left + 135 + bw, y + _SVC_BAR_HT / 2,
                               text=str(cnt), anchor="w",
                               font=("Segoe UI", 8, "bold"), fill="#263238")

    svc_cv.bind("<Configure>", lambda e: _draw_svc(svc_cv, _svc["data"]))

    # Quick Actions
    qa_c = _white_card(right_col, pady_bottom=8)
    qa_i = tk.Frame(qa_c, bg="white")
    qa_i.pack(fill="x", padx=14, pady=14)
    tk.Label(qa_i, text="Quick Actions",
             font=("Segoe UI", 13, "bold"), bg="white", fg="#263238").pack(anchor="w", pady=(0, 10))

    qa_g = tk.Frame(qa_i, bg="white")
    qa_g.pack(fill="x")
    qa_g.columnconfigure(0, weight=1)
    qa_g.columnconfigure(1, weight=1)

    for i, (icon, lbl, page, bg, hv) in enumerate([
        ("", "Triage",        "Triage",        "#43A047", "#2E7D32"),
        ("", "Admitting",     "Admitting",     "#FB8C00", "#EF6C00"),
        ("", "Queue Console", "Queue Console", "#1E88E5", "#1565C0"),
        ("", "OPD Services",  "OPD Services",  "#7B1FA2", "#6A1B9A"),
    ]):
        b = tk.Button(qa_g, text=f"{lbl}",
                      font=("Segoe UI", 10, "bold"), bg=bg, fg="white",
                      bd=0, padx=10, pady=12, cursor="hand2", anchor="w",
                      command=lambda p=page: nav_click(p))
        b.grid(row=i // 2, column=i % 2, sticky="ew", padx=4, pady=4)
        b.bind("<Enter>", lambda e, h=hv: e.widget.config(bg=h))
        b.bind("<Leave>", lambda e, c=bg: e.widget.config(bg=c))

    ss_c = tk.Frame(right_col, bg="#E3F2FD", relief="solid", bd=1)
    ss_c.pack(fill="x", pady=(0, 8))
    ss_l = tk.Label(ss_c, text="Checking server...",
                    font=("Segoe UI", 9), bg="#E3F2FD", fg="#1565C0")
    ss_l.pack(pady=10, padx=12)

    def _chk_srv():
        d = _api_get("/health")
        if is_active["v"]:
            if d:
                parent.after(0, lambda: ss_l.config(
                    text="  System Status: Connected to Server", fg="#2E7D32"))
            else:
                parent.after(0, lambda: ss_l.config(
                    text="  System Status: Cannot reach server", fg="#C62828"))

    threading.Thread(target=_chk_srv, daemon=True).start()

    act_c = tk.Frame(right_col, bg="white", relief="solid", bd=1)
    act_c.pack(fill="both", expand=True, pady=(0, 0))
    act_i = tk.Frame(act_c, bg="white")
    act_i.pack(fill="both", expand=True, padx=14, pady=12)

    act_title_row = tk.Frame(act_i, bg="white")
    act_title_row.pack(fill="x", pady=(0, 4))
    tk.Label(act_title_row, text="Recent Activity",
             font=("Segoe UI", 13, "bold"), bg="white", fg="#263238").pack(side="left")

    act_d_lbl = tk.Label(act_i, text="", font=("Segoe UI", 9),
                         bg="white", fg="#546E7A")
    act_d_lbl.pack(anchor="w", pady=(0, 6))

    style = ttk.Style()
    style.configure("Dash.Treeview", font=("Segoe UI", 9), rowheight=26,
                    background="white", fieldbackground="white")
    style.configure("Dash.Treeview.Heading", font=("Segoe UI", 9, "bold"),
                    background="#E3F2FD", foreground="#1E88E5")
    style.map("Dash.Treeview", background=[("selected", "#1E88E5")])

    tw = tk.Frame(act_i, bg="white")
    tw.pack(fill="both", expand=True)
    tree = ttk.Treeview(tw, columns=("Ticket", "Service", "Status", "Time"),
                        show="headings", style="Dash.Treeview", height=20)
    tree.pack(side="left", fill="both", expand=True)
    act_vsb = ttk.Scrollbar(tw, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=act_vsb.set)
    act_vsb.pack(side="right", fill="y")

    for col, (anch, w) in [("Ticket", ("center", 68)),
                             ("Service", ("w", 120)),
                             ("Status",  ("center", 72)),
                             ("Time",    ("center", 62))]:
        tree.heading(col, text=col)
        tree.column(col, anchor=anch, width=w, minwidth=w - 10)

    def _fetch_activity():
        try:
            day = datetime.strptime(sel_date.get(), "%b %d, %Y").strftime("%b %d, %Y")
        except ValueError:
            return
        d    = _api_get("/activity/list", {"date": day})
        logs = d.get("logs", []) if d else []

        def _apply():
            if not is_active["v"]:
                return
            tree.delete(*tree.get_children())
            act_d_lbl.config(text=f"Activity for {sel_date.get()}")
            if not logs:
                tree.insert("", "end", values=("", "No activity recorded", "", ""))
            else:
                for lg in logs[-60:]:
                    tree.insert("", "end", values=(
                        lg.get("ticket_number", ""),
                        lg.get("service_name", ""),
                        lg.get("status", ""),
                        lg.get("time", ""),
                    ))
                tree.yview_moveto(1)

        if is_active["v"]:
            parent.after(0, _apply)

    rb = tk.Button(act_i, text="  Refresh",
                   font=("Segoe UI", 9, "bold"),
                   bg="#1E88E5", fg="white", bd=0,
                   padx=12, pady=5, cursor="hand2",
                   command=lambda: threading.Thread(
                       target=_fetch_activity, daemon=True).start())
    rb.pack(pady=(8, 0))
    rb.bind("<Enter>", lambda e: rb.config(bg="#1565C0"))
    rb.bind("<Leave>", lambda e: rb.config(bg="#1E88E5"))

    def _on_date_change():
        threading.Thread(target=_fetch_daily_stats, daemon=True).start()
        threading.Thread(target=_fetch_activity,    daemon=True).start()
        threading.Thread(target=_fetch_svc,         daemon=True).start()

    def _fetch_svc():
        try:
            dt  = datetime.strptime(sel_date.get(), "%b %d, %Y")
            dbs = dt.strftime("%Y-%m-%d")
        except ValueError:
            return
        td = _api_get("/tickets/list",  {"today_only": "false"})
        sd = _api_get("/services/list")
        if not td or not sd:
            return
        tickets = [t for t in td.get("tickets", [])
                   if t.get("created_at", "").startswith(dbs)]
        smap   = {s["service_id"]: s for s in sd.get("services", [])}
        scount = {}
        for t in tickets:
            sid = t.get("service_id")
            if sid and sid in smap:
                scount[sid] = scount.get(sid, 0) + 1
        result = sorted(
            [(smap[sid]["service_name"], smap[sid].get("color", "#1E88E5"), cnt)
             for sid, cnt in scount.items()],
            key=lambda x: x[2], reverse=True
        )[:10]
        _svc["data"] = result
        if is_active["v"]:
            parent.after(0, lambda: _draw_svc(svc_cv, result))

    # ═══════════════════════════════════════════════════════════════════
    # DATA ANALYTICS SECTION  –  FIXED VERSION
    # ═══════════════════════════════════════════════════════════════════

    ana_sep = tk.Frame(_sf, bg="#1E88E5", height=40)
    ana_sep.pack(fill="x", padx=0, pady=(12, 0))
    ana_sep.pack_propagate(False)
    tk.Label(ana_sep, text="  Data Analytics",
             font=("Segoe UI", 12, "bold"), bg="#1E88E5", fg="white").pack(
        side="left", padx=18, pady=8)
    tk.Label(ana_sep, text="Service performance insights & trends",
             font=("Segoe UI", 9), bg="#1E88E5", fg="#BBDEFB").pack(side="left")

    # Filter card
    ana_fc  = tk.Frame(_sf, bg="white", relief="solid", bd=1)
    ana_fc.pack(fill="x", padx=15, pady=(6, 6))
    ana_fci = tk.Frame(ana_fc, bg="white")
    ana_fci.pack(fill="x", padx=16, pady=10)

    ana_row = tk.Frame(ana_fci, bg="white")
    ana_row.pack(fill="x")

    def _albl(p, t):
        tk.Label(p, text=t, font=("Segoe UI", 9, "bold"),
                 bg="white", fg="#37474F").pack(side="left", padx=(0, 4))

    _albl(ana_row, "Period:")
    ana_period_var = tk.StringVar(value="This Week")
    ana_period_cb  = ttk.Combobox(ana_row, textvariable=ana_period_var, state="readonly",
                                   font=("Segoe UI", 9), width=13,
                                   values=["Today", "This Week", "This Month",
                                           "Last Month", "Last 3 Months", "Custom Range"])
    ana_period_cb.pack(side="left", padx=(0, 12))

    _albl(ana_row, "From:")
    ana_from_var = tk.StringVar(value=(today - timedelta(days=6)).strftime("%Y-%m-%d"))
    tk.Entry(ana_row, textvariable=ana_from_var, font=("Segoe UI", 9),
             width=11, relief="solid", bd=1).pack(side="left", padx=(0, 8))

    _albl(ana_row, "To:")
    ana_to_var = tk.StringVar(value=today.strftime("%Y-%m-%d"))
    tk.Entry(ana_row, textvariable=ana_to_var, font=("Segoe UI", 9),
             width=11, relief="solid", bd=1).pack(side="left", padx=(0, 12))

    _albl(ana_row, "Service:")
    ana_svc_var = tk.StringVar(value="All Services")
    ana_svc_cb  = ttk.Combobox(ana_row, textvariable=ana_svc_var,
                                state="readonly", font=("Segoe UI", 9), width=20)
    ana_svc_cb.pack(side="left", padx=(0, 12))

    _albl(ana_row, "Chart:")
    ana_chart_var = tk.StringVar(value="Bar + Pie")
    ttk.Combobox(ana_row, textvariable=ana_chart_var, state="readonly",
                 font=("Segoe UI", 9), width=12,
                 values=["Bar + Pie", "Bar Only", "Pie Only",
                         "Line Trend", "Stacked Bar"]).pack(side="left", padx=(0, 12))

    def _ana_btn(p, text, bg, hv, cmd):
        b = tk.Button(p, text=text, font=("Segoe UI", 9, "bold"),
                      bg=bg, fg="white", bd=0, padx=12, pady=5,
                      cursor="hand2", relief="flat", command=cmd)
        b.pack(side="left", padx=(0, 6))
        b.bind("<Enter>", lambda e: b.config(bg=hv))
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        return b

    ana_apply_btn  = _ana_btn(ana_row, "Apply",        "#1E88E5", "#1565C0", lambda: ana_do_apply())
    ana_print_btn  = _ana_btn(ana_row, "Print Report", "#37474F", "#263238", lambda: ana_do_print())
    ana_export_btn = _ana_btn(ana_row, "Export CSV",   "#00838F", "#006064", lambda: ana_do_export())

    def _ana_on_period(event=None):
        p = ana_period_var.get()
        t = today.date()
        if p == "Today":
            s, e = str(t), str(t)
        elif p == "This Week":
            s, e = str(t - timedelta(days=t.weekday())), str(t)
        elif p == "This Month":
            s, e = str(t.replace(day=1)), str(t)
        elif p == "Last Month":
            first = t.replace(day=1); last = first - timedelta(days=1)
            s, e  = str(last.replace(day=1)), str(last)
        elif p == "Last 3 Months":
            s, e = str((t.replace(day=1) - timedelta(days=90)).replace(day=1)), str(t)
        else:
            return
        ana_from_var.set(s); ana_to_var.set(e)

    ana_period_cb.bind("<<ComboboxSelected>>", _ana_on_period)

    # KPI row
    ana_kpi_frame = tk.Frame(_sf, bg="#F4F6F8")
    ana_kpi_frame.pack(fill="x", padx=15, pady=(0, 6))
    for i in range(4):
        ana_kpi_frame.columnconfigure(i, weight=1, uniform="anakpi")

    ana_kpi_vars = {}
    for col, (lbl, key, color) in enumerate([
        ("Total Served", "total", "#43A047"),
        ("Top Service",  "top",   "#1E88E5"),
        ("Peak Day",     "peak",  "#FB8C00"),
        ("Avg / Day",    "avg",   "#7B1FA2"),
    ]):
        kf = tk.Frame(ana_kpi_frame, bg=color)
        kf.grid(row=0, column=col, sticky="nsew", padx=5, pady=4)
        ki = tk.Frame(kf, bg=color)
        ki.pack(fill="both", expand=True, padx=10, pady=8)
        v = tk.StringVar(value="--")
        tk.Label(ki, textvariable=v, font=("Segoe UI", 20, "bold"),
                 bg=color, fg="white").pack()
        tk.Label(ki, text=lbl, font=("Segoe UI", 8), bg=color, fg="white").pack()
        ana_kpi_vars[key] = v

    # Chart card
    ana_chart_card = tk.Frame(_sf, bg="white", relief="solid", bd=1)
    ana_chart_card.pack(fill="x", padx=15, pady=(0, 6))
    ana_chart_hdr  = tk.Frame(ana_chart_card, bg="#E3F2FD")
    ana_chart_hdr.pack(fill="x")
    tk.Label(ana_chart_hdr, text="  Charts",
             font=("Segoe UI", 10, "bold"),
             bg="#E3F2FD", fg="#1E88E5").pack(side="left", padx=12, pady=6)

    if not HAS_MATPLOTLIB:
        tk.Label(ana_chart_card,
                 text="matplotlib not installed. Run:  pip install matplotlib",
                 font=("Segoe UI", 10), bg="white", fg="#E53935").pack(pady=20)

    ana_chart_host = tk.Frame(ana_chart_card, bg="white")
    ana_chart_host.pack(fill="both", expand=True, padx=4, pady=4)

    # Thread-safe ref holder — only touched from main thread via after()
    _ana_cv_ref = {"widget": None, "fig": None}

    # Data table card
    ana_tbl_card = tk.Frame(_sf, bg="white", relief="solid", bd=1)
    ana_tbl_card.pack(fill="x", padx=15, pady=(0, 15))
    ana_tbl_hdr  = tk.Frame(ana_tbl_card, bg="#E3F2FD")
    ana_tbl_hdr.pack(fill="x")
    tk.Label(ana_tbl_hdr, text="  Detailed Data Table",
             font=("Segoe UI", 10, "bold"),
             bg="#E3F2FD", fg="#1E88E5").pack(side="left", padx=12, pady=6)

    ana_t_cols = ("Service", "Total Served", "Daily Avg", "Peak Day", "Skipped", "% of Total")
    ana_style  = ttk.Style()
    ana_style.configure("Ana2.Treeview", font=("Segoe UI", 9), rowheight=24,
                        background="white", fieldbackground="white")
    ana_style.configure("Ana2.Treeview.Heading", font=("Segoe UI", 9, "bold"),
                        background="#E3F2FD", foreground="#1E88E5")
    ana_style.map("Ana2.Treeview", background=[("selected", "#1E88E5")])

    ana_data_tv = ttk.Treeview(ana_tbl_card, columns=ana_t_cols, show="headings",
                                style="Ana2.Treeview", height=5)
    for c, w in zip(ana_t_cols, [200, 100, 90, 100, 80, 90]):
        ana_data_tv.heading(c, text=c)
        ana_data_tv.column(c, width=w, anchor="center")
    ana_data_tv.pack(fill="x", padx=10, pady=(4, 10))

    _ana_state = {"records": [], "dates": []}

    _ANA_CHART_COLORS = [
        "#1E88E5", "#43A047", "#FB8C00", "#E53935", "#7B1FA2",
        "#00ACC1", "#FDD835", "#5E35B1", "#D81B60", "#00897B",
        "#F4511E", "#8D6E63", "#546E7A", "#558B2F", "#FFB300",
    ]

    # ── helpers ──────────────────────────────────────────────────────

    def _ana_resolve_dates():
        """Return (from_str, to_str) in YYYY-MM-DD based on current period selection."""
        p = ana_period_var.get()
        t = today.date()
        if p == "Today":
            return str(t), str(t)
        elif p == "This Week":
            return str(t - timedelta(days=t.weekday())), str(t)
        elif p == "This Month":
            return str(t.replace(day=1)), str(t)
        elif p == "Last Month":
            first = t.replace(day=1)
            last  = first - timedelta(days=1)
            return str(last.replace(day=1)), str(last)
        elif p == "Last 3 Months":
            return str((t.replace(day=1) - timedelta(days=90)).replace(day=1)), str(t)
        else:  # Custom Range — validate entries
            s = ana_from_var.get().strip()
            e = ana_to_var.get().strip()
            try:
                datetime.strptime(s, "%Y-%m-%d")
                datetime.strptime(e, "%Y-%m-%d")
            except ValueError:
                return str(t), str(t)
            return s, e

    def _ana_date_list(s, e):
        """Return list of YYYY-MM-DD strings from s to e inclusive."""
        try:
            from datetime import date as _date
            start = datetime.strptime(s, "%Y-%m-%d").date()
            end   = datetime.strptime(e, "%Y-%m-%d").date()
            if start > end:
                start, end = end, start        # swap if reversed
            out, cur = [], start
            while cur <= end:
                out.append(str(cur))
                cur += timedelta(days=1)
            return out
        except Exception:
            return []

    # ── data fetcher (runs in worker thread) ─────────────────────────

    def _ana_fetch():
        s, e  = _ana_resolve_dates()
        dates = _ana_date_list(s, e)
        if not dates:
            return [], []

        svcs_d   = _api_get("/services/list")
        all_svcs = svcs_d.get("services", []) if svcs_d else []
        svc_by_name = {sv["service_name"]: sv for sv in all_svcs}
        svc_by_id   = {sv["service_id"]:   sv for sv in all_svcs}

        tkt_d    = _api_get("/tickets/list", {"today_only": "false"})
        all_tkts = tkt_d.get("tickets", []) if tkt_d else []

        served_counts  = {}
        skipped_counts = {}

        date_set = set(dates)
        for t in all_tkts:
            raw = t.get("created_at", "")
            tdate = raw[:10]
            if tdate not in date_set:
                continue
            sid   = t.get("service_id")
            svc   = svc_by_id.get(sid)
            if not svc:
                sname = t.get("service_name", "")
                svc   = svc_by_name.get(sname)
            if not svc:
                continue
            sname  = svc["service_name"]
            status = t.get("status", "")
            key    = (tdate, sname)
            if status == "Served":
                served_counts[key]  = served_counts.get(key, 0)  + 1
            elif status == "Skipped":
                skipped_counts[key] = skipped_counts.get(key, 0) + 1

        for d in dates:
            fmt    = datetime.strptime(d, "%Y-%m-%d").strftime("%b %d, %Y")
            logs_d = _api_get("/activity/list", {"date": fmt})
            if not logs_d:
                continue
            for lg in logs_d.get("logs", []):
                action = lg.get("action", "")
                sname  = lg.get("service_name", "")
                if not sname or sname not in svc_by_name:
                    continue
                key = (d, sname)
                if action == "Skip" and skipped_counts.get(key, 0) == 0:
                    skipped_counts[key] = skipped_counts.get(key, 0) + 1

        all_keys = set(served_counts.keys()) | set(skipped_counts.keys())
        records  = []
        for (d, sname) in sorted(all_keys):
            svc  = svc_by_name.get(sname, {})
            records.append({
                "date":         d,
                "service_name": sname,
                "service_code": svc.get("service_code", ""),
                "served":       served_counts.get((d, sname), 0),
                "skipped":      skipped_counts.get((d, sname), 0),
            })

        return records, dates

    # ── chart embed (main thread only) ───────────────────────────────

    def _ana_embed(fig):
        """Safely replace the chart canvas. Must be called from main thread."""
        if not is_active["v"]:
            try:
                plt.close(fig)
            except Exception:
                pass
            return
        old_widget = _ana_cv_ref.get("widget")
        old_fig    = _ana_cv_ref.get("fig")
        if old_widget:
            try:
                old_widget.get_tk_widget().destroy()
            except Exception:
                pass
        if old_fig and old_fig is not fig:
            try:
                plt.close(old_fig)
            except Exception:
                pass
        _ana_cv_ref["widget"] = None
        _ana_cv_ref["fig"]    = None

        try:
            cv = FigureCanvasTkAgg(fig, master=ana_chart_host)
            cv.draw()
            w = cv.get_tk_widget()
            w.configure(bg="white")
            w.pack(fill="both", expand=True)
            _ana_cv_ref["widget"] = cv
            _ana_cv_ref["fig"]    = fig
        except Exception as ex:
            print(f"[ANA] embed error: {ex}")
            try:
                plt.close(fig)
            except Exception:
                pass

    # ── chart drawing helpers ─────────────────────────────────────────

    def _ana_bar(ax, names, totals, colors, title):
        ax.set_facecolor("#FAFAFA")
        if not names:
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                    transform=ax.transAxes, fontsize=12, color="#9E9E9E")
            ax.axis("off")
            return
        xs   = list(range(len(names)))
        bars = ax.bar(xs, totals, color=colors,
                      width=0.55, edgecolor="white", linewidth=1.2, zorder=3)
        ax.set_xticks(xs)
        ax.set_xticklabels(names, rotation=28, ha="right",
                           fontsize=8, fontweight="bold", color="#263238")
        ax.set_ylabel("Patients Served", fontsize=9, color="#546E7A")
        ax.set_title(title, fontsize=11, fontweight="bold", color="#1A237E", pad=10)
        ax.yaxis.grid(True, linestyle="--", alpha=0.4, color="#CFD8DC", zorder=0)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["left", "bottom"]].set_edgecolor("#CFD8DC")
        ax.tick_params(axis="y", labelsize=8, colors="#546E7A")
        ax.tick_params(axis="x", length=0)
        max_val = max(totals) if totals else 1
        ax.set_ylim(0, max_val * 1.18)
        for bar, val in zip(bars, totals):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max_val * 0.02,
                        str(val), ha="center", va="bottom",
                        fontsize=8, fontweight="bold", color="#263238")

    def _ana_pie(ax, names, totals, colors):
        if not names or sum(totals) == 0:
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                    transform=ax.transAxes, fontsize=12, color="#9E9E9E")
            ax.axis("off")
            return
        _, _, autotexts = ax.pie(
            totals, labels=None, colors=colors,
            autopct=lambda p: f"{p:.1f}%" if p > 3 else "",
            startangle=140,
            wedgeprops={"edgecolor": "white", "linewidth": 2},
            pctdistance=0.78
        )
        for at in autotexts:
            at.set_fontsize(8)
            at.set_fontweight("bold")
            at.set_color("white")
        ax.set_title("Service Distribution", fontsize=11, fontweight="bold",
                     color="#1A237E", pad=10)
        n_extra = max(0, len(names) - 5)
        patches = [mpatches.Patch(color=c, label=n[:20]) for c, n in zip(colors, names)]
        ax.legend(handles=patches, loc="lower center",
                  bbox_to_anchor=(0.5, -0.22 - 0.05 * n_extra),
                  ncol=2, fontsize=7.5, frameon=False)

    def _ana_line(ax, svc_by_date, dates, colors, sel_filter):
        ax.set_facecolor("#FAFAFA")
        if not dates:
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                    transform=ax.transAxes, fontsize=12, color="#9E9E9E")
            ax.axis("off")
            return
        plotted = 0
        for i, (name, by_date) in enumerate(svc_by_date.items()):
            if sel_filter != "All Services" and name != sel_filter:
                continue
            vals = [by_date.get(d, 0) for d in dates]
            if sum(vals) == 0:
                continue
            ax.plot(range(len(dates)), vals, marker="o", markersize=4,
                    linewidth=2, label=name[:20],
                    color=_ANA_CHART_COLORS[i % len(_ANA_CHART_COLORS)])
            plotted += 1
        if plotted == 0:
            ax.text(0.5, 0.5, "No data for selected filter",
                    ha="center", va="center",
                    transform=ax.transAxes, fontsize=12, color="#9E9E9E")
        step = max(1, len(dates) // 7)
        ax.set_xticks(range(0, len(dates), step))
        ax.set_xticklabels(
            [datetime.strptime(dates[j], "%Y-%m-%d").strftime("%b %d")
             for j in range(0, len(dates), step)],
            rotation=30, ha="right", fontsize=8)
        ax.set_ylabel("Patients Served", fontsize=9, color="#546E7A")
        ax.set_title("Daily Trend by Service", fontsize=11, fontweight="bold",
                     color="#1A237E", pad=10)
        ax.yaxis.grid(True, linestyle="--", alpha=0.4, color="#CFD8DC")
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=8, colors="#546E7A")
        if plotted:
            ax.legend(fontsize=7.5, frameon=False, loc="upper left")

    def _ana_stacked(ax, svc_by_date, dates, colors, names):
        ax.set_facecolor("#FAFAFA")
        if not dates or not names:
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                    transform=ax.transAxes, fontsize=12, color="#9E9E9E")
            ax.axis("off")
            return
        bottoms = [0] * len(dates)
        plotted = 0
        for i, name in enumerate(names):
            by_date = svc_by_date.get(name, {})
            vals    = [by_date.get(d, 0) for d in dates]
            if sum(vals) == 0:
                continue
            ax.bar(range(len(dates)), vals, bottom=bottoms,
                   color=_ANA_CHART_COLORS[i % len(_ANA_CHART_COLORS)],
                   label=name[:18], edgecolor="white", linewidth=0.7)
            bottoms = [b + v for b, v in zip(bottoms, vals)]
            plotted += 1
        if plotted == 0:
            ax.text(0.5, 0.5, "No data", ha="center", va="center",
                    transform=ax.transAxes, fontsize=12, color="#9E9E9E")
        step = max(1, len(dates) // 7)
        ax.set_xticks(range(0, len(dates), step))
        ax.set_xticklabels(
            [datetime.strptime(dates[j], "%Y-%m-%d").strftime("%b %d")
             for j in range(0, len(dates), step)],
            rotation=30, ha="right", fontsize=8)
        ax.set_ylabel("Patients Served", fontsize=9, color="#546E7A")
        ax.set_title("Stacked Daily Volume", fontsize=11, fontweight="bold",
                     color="#1A237E", pad=10)
        ax.yaxis.grid(True, linestyle="--", alpha=0.4, color="#CFD8DC")
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=8, colors="#546E7A")
        if plotted:
            ax.legend(fontsize=7.5, frameon=False, loc="upper left", ncol=2)

    # ── main chart builder (runs in worker thread) ────────────────────

    def _ana_build_charts(records, dates):
        """Compute aggregates and create the matplotlib Figure, then schedule embed."""
        if not HAS_MATPLOTLIB:
            return

        sel_filter = ana_svc_var.get()

        svc_totals  = {}
        svc_by_date = {}
        svc_skip    = {}

        for r in records:
            name = r["service_name"]
            if sel_filter != "All Services" and name != sel_filter:
                continue
            svc_totals[name]  = svc_totals.get(name, 0) + r["served"]
            svc_skip[name]    = svc_skip.get(name, 0)   + r["skipped"]
            svc_by_date.setdefault(name, {})
            d = r["date"]
            svc_by_date[name][d] = svc_by_date[name].get(d, 0) + r["served"]

        grand  = sum(svc_totals.values()) or 1
        n_days = max(len(dates), 1)

        top      = max(svc_totals, key=svc_totals.get) if svc_totals else "--"
        day_tots = {}
        for by_date in svc_by_date.values():
            for d, cnt in by_date.items():
                day_tots[d] = day_tots.get(d, 0) + cnt
        peak_day = max(day_tots, key=day_tots.get) if day_tots else "--"
        if peak_day != "--":
            try:
                peak_day = datetime.strptime(peak_day, "%Y-%m-%d").strftime("%b %d")
            except Exception:
                pass

        kpi_total = str(sum(svc_totals.values()))
        kpi_top   = (top[:16] if top != "--" else "--")
        kpi_peak  = peak_day
        kpi_avg   = str(round(sum(svc_totals.values()) / n_days, 1))

        table_rows = []
        for i, (name, tot) in enumerate(sorted(svc_totals.items(), key=lambda x: -x[1])):
            by_date   = svc_by_date.get(name, {})
            peak      = max(by_date, key=by_date.get) if by_date else "--"
            try:
                peak = datetime.strptime(peak, "%Y-%m-%d").strftime("%b %d")
            except Exception:
                pass
            table_rows.append((
                name,
                tot,
                round(tot / n_days, 1),
                peak,
                svc_skip.get(name, 0),
                f"{round(tot / grand * 100, 1)}%"
            ))

        names  = list(svc_totals.keys())
        totals = [svc_totals[n] for n in names]
        colors = [_ANA_CHART_COLORS[i % len(_ANA_CHART_COLORS)] for i in range(len(names))]
        ctype  = ana_chart_var.get()

        try:
            if not svc_totals:
                fig = Figure(figsize=(10, 2.5), dpi=96, facecolor="white")
                ax  = fig.add_subplot(111)
                ax.axis("off")
                ax.text(0.5, 0.5, "No data available for the selected period.",
                        ha="center", va="center", fontsize=12, color="#9E9E9E",
                        transform=ax.transAxes)
            elif ctype == "Bar Only":
                fig = Figure(figsize=(10, 4), dpi=96, facecolor="white")
                _ana_bar(fig.add_subplot(111), names, totals, colors,
                         "Patients Served by Service")
            elif ctype == "Pie Only":
                fig = Figure(figsize=(7, 4.5), dpi=96, facecolor="white")
                _ana_pie(fig.add_subplot(111), names, totals, colors)
            elif ctype == "Line Trend":
                fig = Figure(figsize=(10, 4), dpi=96, facecolor="white")
                _ana_line(fig.add_subplot(111), svc_by_date, dates, colors, sel_filter)
            elif ctype == "Stacked Bar":
                fig = Figure(figsize=(10, 4), dpi=96, facecolor="white")
                _ana_stacked(fig.add_subplot(111), svc_by_date, dates, colors, names)
            else:  # Bar + Pie (default)
                fig = Figure(figsize=(12, 4.2), dpi=96, facecolor="white")
                gs  = gridspec.GridSpec(1, 2, width_ratios=[3, 2], figure=fig,
                                        left=0.06, right=0.97, wspace=0.30)
                _ana_bar(fig.add_subplot(gs[0]), names, totals, colors, "Served by Service")
                _ana_pie(fig.add_subplot(gs[1]), names, totals, colors)

            fig.patch.set_facecolor("white")
        except Exception as ex:
            print(f"[ANA] chart build error: {ex}")
            fig = Figure(figsize=(10, 2.5), dpi=96, facecolor="white")
            ax  = fig.add_subplot(111)
            ax.axis("off")
            ax.text(0.5, 0.5, f"Chart error: {ex}",
                    ha="center", va="center", fontsize=10, color="#E53935",
                    transform=ax.transAxes)

        def _apply_ui():
            if not is_active["v"]:
                try:
                    plt.close(fig)
                except Exception:
                    pass
                return
            ana_kpi_vars["total"].set(kpi_total)
            ana_kpi_vars["top"].set(kpi_top)
            ana_kpi_vars["peak"].set(kpi_peak)
            ana_kpi_vars["avg"].set(kpi_avg)
            ana_data_tv.delete(*ana_data_tv.get_children())
            for i, row in enumerate(table_rows):
                tag = "alt" if i % 2 else ""
                ana_data_tv.tag_configure("alt", background="#F5F9FF")
                ana_data_tv.insert("", "end", tags=(tag,), values=row)
            _ana_embed(fig)

        if is_active["v"]:
            parent.after(0, _apply_ui)

    # ── apply / print / export ────────────────────────────────────────

    def ana_do_apply():
        """Kick off a full analytics refresh."""
        if not is_active["v"]:
            return
        ana_apply_btn.config(text="Loading...", state="disabled")
        for v in ana_kpi_vars.values():
            v.set("...")

        def _worker():
            try:
                records, dates = _ana_fetch()
                _ana_state["records"] = records
                _ana_state["dates"]   = dates
                _ana_build_charts(records, dates)
            except Exception as ex:
                print(f"[ANA] worker error: {ex}")
            finally:
                if is_active["v"]:
                    parent.after(0, lambda: ana_apply_btn.config(
                        text="Apply", state="normal"))

        threading.Thread(target=_worker, daemon=True).start()

    def ana_do_print():
        if not HAS_MATPLOTLIB:
            messagebox.showerror("Error", "matplotlib required.\nRun: pip install matplotlib")
            return
        records    = _ana_state.get("records", [])
        dates      = _ana_state.get("dates",   [])
        s, e       = _ana_resolve_dates()
        sel_filter = ana_svc_var.get()

        svc_totals  = {}
        svc_by_date = {}
        svc_skip    = {}
        for r in records:
            name = r["service_name"]
            if sel_filter != "All Services" and name != sel_filter:
                continue
            svc_totals[name]  = svc_totals.get(name, 0) + r["served"]
            svc_skip[name]    = svc_skip.get(name, 0)   + r["skipped"]
            svc_by_date.setdefault(name, {})
            svc_by_date[name][r["date"]] = svc_by_date[name].get(r["date"], 0) + r["served"]

        names  = list(svc_totals.keys())
        totals = [svc_totals[n] for n in names]
        colors = [_ANA_CHART_COLORS[i % len(_ANA_CHART_COLORS)] for i in range(len(names))]
        grand  = sum(totals) or 1
        n_days = max(len(dates), 1)

        try:
            fig_p = plt.figure(figsize=(11, 8.5), facecolor="white")
            fig_p.subplots_adjust(top=0.87, bottom=0.12, left=0.08,
                                  right=0.95, hspace=0.45, wspace=0.35)
            fig_p.text(0.5, 0.94, "ILOCOS SUR MEDICAL CENTER - OPD Analytics Report",
                       ha="center", va="top", fontsize=14, fontweight="bold", color="#1A237E")
            fig_p.text(0.5, 0.905,
                       f"Period: {s}  to  {e}     |     "
                       f"Generated: {datetime.now().strftime('%B %d, %Y  %I:%M %p')}",
                       ha="center", va="top", fontsize=9, color="#546E7A")
            if names:
                _ana_bar(fig_p.add_subplot(2, 2, 1), names, totals, colors, "Served by Service")
                _ana_pie(fig_p.add_subplot(2, 2, 2), names, totals, colors)
                _ana_line(fig_p.add_subplot(2, 1, 2), svc_by_date, dates, colors, sel_filter)
                tbl_data = [
                    [nm[:24], str(tot), str(round(tot / n_days, 1)),
                     str(svc_skip.get(nm, 0)), f"{round(tot / grand * 100, 1)}%"]
                    for nm, tot in sorted(svc_totals.items(), key=lambda x: -x[1])
                ]
                if tbl_data:
                    ax_t = fig_p.add_axes([0.08, 0.01, 0.87, 0.08])
                    ax_t.axis("off")
                    tbl = ax_t.table(
                        cellText=tbl_data,
                        colLabels=["Service", "Served", "Avg/Day", "Skipped", "% Share"],
                        loc="center", cellLoc="center")
                    tbl.auto_set_font_size(False)
                    tbl.set_fontsize(7.5)
                    tbl.scale(1, 1.3)
                    for (row, col), cell in tbl.get_celld().items():
                        if row == 0:
                            cell.set_facecolor("#1E88E5")
                            cell.set_text_props(color="white", fontweight="bold")
                        else:
                            cell.set_facecolor("#F5F9FF" if row % 2 else "white")
                        cell.set_edgecolor("#CFD8DC")
            else:
                fig_p.text(0.5, 0.5, "No data available for selected period.",
                           ha="center", va="center", fontsize=14, color="#9E9E9E")

            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            fig_p.savefig(tmp.name, format="pdf", bbox_inches="tight", dpi=150)
            plt.close(fig_p)
            tmp.close()

            import sys, subprocess
            if sys.platform == "win32":
                os.startfile(tmp.name, "print")
            elif sys.platform == "darwin":
                subprocess.run(["lpr", tmp.name])
            else:
                subprocess.run(["lpr", tmp.name])
            messagebox.showinfo("Print",
                                f"Report sent to printer.\n\nPDF saved at:\n{tmp.name}")
        except Exception as ex:
            messagebox.showerror("Print Error", f"Could not generate report:\n{ex}")

    def ana_do_export():
        try:
            import csv
            from tkinter import filedialog
            s, e = _ana_resolve_dates()
            path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                initialfile=f"ISMC_Analytics_{s}_to_{e}.csv")
            if not path:
                return
            records    = _ana_state.get("records", [])
            sel_filter = ana_svc_var.get()
            with open(path, "w", newline="", encoding="utf-8") as f:
                wr = csv.writer(f)
                wr.writerow(["Date", "Service", "Code", "Served", "Skipped"])
                for r in records:
                    if sel_filter != "All Services" and r["service_name"] != sel_filter:
                        continue
                    wr.writerow([r["date"], r["service_name"],
                                 r["service_code"], r["served"], r["skipped"]])
            messagebox.showinfo("Export", f"CSV exported:\n{path}")
        except Exception as ex:
            messagebox.showerror("Export Error", str(ex))

    def _ana_load_svc_filter():
        d = _api_get("/services/list")
        if d and d.get("success") and is_active["v"]:
            names = ["All Services"] + [sv["service_name"] for sv in d.get("services", [])]
            parent.after(0, lambda: ana_svc_cb.config(values=names))

    # ── END DATA ANALYTICS SECTION ────────────────────────────────────

    safe_after(50,    lambda: threading.Thread(target=_fetch_metrics,       daemon=True).start())
    safe_after(100,   lambda: threading.Thread(target=_preload_act_dates,   daemon=True).start())
    safe_after(200,   lambda: threading.Thread(target=_fetch_trend,         daemon=True).start())
    safe_after(300,   lambda: threading.Thread(target=_fetch_daily_stats,   daemon=True).start())
    safe_after(400,   lambda: threading.Thread(target=_fetch_activity,      daemon=True).start())
    safe_after(500,   lambda: threading.Thread(target=_fetch_svc,           daemon=True).start())
    safe_after(600,   lambda: threading.Thread(target=_ana_load_svc_filter, daemon=True).start())
    safe_after(700,   lambda: ana_do_apply())

    def _auto_refresh():
        if not is_active["v"]:
            return
        threading.Thread(target=_fetch_metrics,  daemon=True).start()
        threading.Thread(target=_fetch_activity, daemon=True).start()
        safe_after(30_000, _auto_refresh)

    safe_after(30_000, _auto_refresh)

#  UI UTILITIES

def _white_card(parent, pady_bottom=8):
    c = tk.Frame(parent, bg="white", relief="solid", bd=1)
    c.pack(fill="x", pady=(0, pady_bottom))
    return c


def _card(parent, builder_fn):
    outer = tk.Frame(parent, bg="#F4F6F8")
    outer.pack(fill="x", padx=15, pady=(15, 8))
    card = tk.Frame(outer, bg="white", relief="solid", bd=1)
    card.pack(fill="x")
    inner = tk.Frame(card, bg="white")
    inner.pack(fill="x", padx=18, pady=14)
    builder_fn(inner)


def _build_announcement_block(frame, parent, is_active):
    title_row = tk.Frame(frame, bg="white")
    title_row.pack(fill="x", pady=(0, 10))
    tk.Label(title_row, text="  Display Screen Announcement",
             font=("Segoe UI", 13, "bold"), bg="white", fg="#263238").pack(side="left")

    tk.Label(frame, text="Message:", font=("Segoe UI", 10),
             bg="white", fg="#546E7A").pack(anchor="w", pady=(0, 4))

    entry = tk.Entry(frame, font=("Segoe UI", 11), bd=1, relief="solid")
    entry.pack(fill="x", ipady=8)

    banner = tk.Frame(frame, bg="#E8F5E9", relief="solid", bd=1)
    banner.pack(fill="x", pady=(10, 0))
    tk.Label(banner, text="Current:", font=("Segoe UI", 9, "bold"),
             bg="#E8F5E9", fg="#2E7D32").pack(side="left", padx=(10, 6), pady=8)
    cur_lbl = tk.Label(banner, text="Loading...",
                       font=("Segoe UI", 10), bg="#E8F5E9", fg="#263238",
                       wraplength=900, justify="left", anchor="w")
    cur_lbl.pack(side="left", fill="x", expand=True, pady=8, padx=(0, 10))

    def _reload():
        def _fetch():
            d   = _api_get("/announcements/current")
            msg = d.get("message", "No announcement set") if d else "No announcement set"
            if is_active["v"]:
                parent.after(0, lambda: cur_lbl.config(
                    text=msg if msg else "No announcement set"))
        threading.Thread(target=_fetch, daemon=True).start()

    def _save():
        msg = entry.get().strip()
        if not msg:
            messagebox.showwarning("Empty", "Please enter a message.", parent=parent)
            return
        def _do():
            r = _api_post("/announcements/update", {"message": msg})
            if is_active["v"]:
                if r and r.get("success"):
                    parent.after(0, lambda: (
                        messagebox.showinfo("Success", "Announcement updated!"),
                        entry.delete(0, tk.END),
                        _reload()
                    ))
                else:
                    parent.after(0, lambda: messagebox.showerror(
                        "Error", "Failed to save.", parent=parent))
        threading.Thread(target=_do, daemon=True).start()

    def _clear():
        def _do():
            _api_post("/announcements/update",
                      {"message": "Welcome to ISMC OPD. Please wait for your ticket number to be called."})
            if is_active["v"]:
                parent.after(0, lambda: (entry.delete(0, tk.END), _reload()))
        threading.Thread(target=_do, daemon=True).start()

    btn_row = tk.Frame(frame, bg="white")
    btn_row.pack(fill="x", pady=(10, 0))
    for text, bg, hv, cmd in [
        ("Update Announcement", "#1E88E5", "#1565C0", _save),
        ("Clear Announcement",  "#E53935", "#B71C1C", _clear),
    ]:
        b = tk.Button(btn_row, text=text, font=("Segoe UI", 10, "bold"),
                      bg=bg, fg="white", bd=0, padx=18, pady=8,
                      cursor="hand2", command=cmd)
        b.pack(side="left", padx=(0, 8))
        b.bind("<Enter>", lambda e, h=hv: e.widget.config(bg=h))
        b.bind("<Leave>", lambda e, c=bg: e.widget.config(bg=c))

    _reload()