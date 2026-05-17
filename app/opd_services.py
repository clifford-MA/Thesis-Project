import tkinter as tk
from tkinter import ttk, colorchooser, messagebox
import requests
import threading
import sys
import os

try:
    import __main__
    if hasattr(__main__, 'API_BASE_URL'):
        API_URL = __main__.API_BASE_URL
        REQUEST_TIMEOUT = __main__.REQUEST_TIMEOUT
    else:
        from config import API_BASE_URL as API_URL, REQUEST_TIMEOUT
except:
    API_URL = "http://localhost:5000/api"
    REQUEST_TIMEOUT = 10


# HELPER
def force_popup_to_parent_screen(popup_window, parent_widget):
    """Force popup to appear on the same screen as parent window"""
    popup_window.update_idletasks()
    parent_root   = parent_widget.winfo_toplevel()
    parent_x      = parent_root.winfo_x()
    parent_y      = parent_root.winfo_y()
    parent_width  = parent_root.winfo_width()
    parent_height = parent_root.winfo_height()
    parent_center_x = parent_x + (parent_width  // 2)
    parent_center_y = parent_y + (parent_height // 2)
    popup_width  = popup_window.winfo_width()
    popup_height = popup_window.winfo_height()
    x = parent_center_x - (popup_width  // 2)
    y = parent_center_y - (popup_height // 2)
    x = max(parent_x, min(x, parent_x + parent_width  - popup_width))
    y = max(parent_y, min(y, parent_y + parent_height - popup_height))
    popup_window.geometry(f"+{x}+{y}")


# Add/Edit Service Popup
def add_service_popup(parent_frame, service=None):
    is_edit = service is not None

    popup = tk.Toplevel()
    popup.title("Add OPD Service" if not is_edit else "Edit OPD Service")
    popup.configure(bg="#F4F6F8")
    popup.resizable(True, True)

    screen_w = popup.winfo_screenwidth()
    screen_h = popup.winfo_screenheight()

    popup_w = max(380, min(500, int(screen_w * 0.38)))
    popup_h = max(460, min(640, int(screen_h * 0.72)))

    popup.minsize(360, 440)

    popup.geometry(f"{popup_w}x{popup_h}")
    force_popup_to_parent_screen(popup, parent_frame)

    # Font / spacing
    title_fs  = max(13, min(16, int(popup_w * 0.034)))
    label_fs  = max(10, min(12, int(popup_w * 0.026)))
    btn_fs    = max(11, min(13, int(popup_w * 0.028)))
    padx      = max(18, int(popup_w * 0.042))
    entry_ipy = max(9,  int(popup_h * 0.018))

    # Outer container
    outer = tk.Frame(popup, bg="#F4F6F8")
    outer.pack(fill="both", expand=True, padx=10, pady=10)

    # White card
    card = tk.Frame(outer, bg="white", bd=2, relief="ridge")
    card.pack(fill="both", expand=True)

    # Title bar
    title_bar = tk.Frame(card, bg="white")
    title_bar.pack(fill="x", padx=padx, pady=(16, 4))
    tk.Label(title_bar,
             text="Add OPD Service" if not is_edit else "Edit OPD Service",
             font=("Segoe UI", title_fs, "bold"),
             bg="white", fg="#263238").pack()

    tk.Frame(card, bg="#E0E0E0", height=1).pack(fill="x", padx=padx, pady=(4, 0))

    # Scrollable form body
    body_frame = tk.Frame(card, bg="white")
    body_frame.pack(fill="both", expand=True)

    body_canvas = tk.Canvas(body_frame, bg="white", highlightthickness=0)
    body_vsb    = ttk.Scrollbar(body_frame, orient="vertical",
                                command=body_canvas.yview)
    scroll_inner = tk.Frame(body_canvas, bg="white")

    scroll_inner.bind(
        "<Configure>",
        lambda e: body_canvas.configure(scrollregion=body_canvas.bbox("all"))
    )
    body_canvas.create_window((0, 0), window=scroll_inner, anchor="nw")
    body_canvas.configure(yscrollcommand=body_vsb.set)

    body_canvas.pack(side="left", fill="both", expand=True)
    body_vsb.pack(side="right", fill="y")

    def _wheel(e):
        body_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
    body_canvas.bind_all("<MouseWheel>", _wheel)
    popup.bind("<Destroy>", lambda e: body_canvas.unbind_all("<MouseWheel>")
               if e.widget == popup else None)

    body_canvas.bind(
        "<Configure>",
        lambda e: body_canvas.itemconfig(
            body_canvas.find_withtag("all")[0] if body_canvas.find_withtag("all") else None,
            width=e.width) if body_canvas.find_withtag("all") else None
    )

    # Form fields
    def _field_label(text):
        tk.Label(scroll_inner, text=text, bg="white", fg="#37474F",
                 font=("Segoe UI", label_fs, "bold")).pack(
                     anchor="w", padx=padx, pady=(14, 3))

    def _entry():
        e = ttk.Entry(scroll_inner, font=("Segoe UI", label_fs))
        e.pack(fill="x", padx=padx, ipady=entry_ipy)
        return e

    _field_label("Service Name:")
    name_entry = _entry()

    _field_label("Service Code:")
    code_entry = _entry()

    # Color picker row
    _field_label("Color:")
    color_var     = tk.StringVar(value="#1E88E5")

    color_row = tk.Frame(scroll_inner, bg="white")
    color_row.pack(padx=padx, pady=(4, 0), anchor="w")

    color_preview = tk.Label(color_row, text="        ",
                             bg="#1E88E5", bd=2, relief="solid",
                             width=4, height=1)
    color_preview.pack(side="left", padx=(0, 10), ipady=6)

    def pick_color():
        color = colorchooser.askcolor(initialcolor=color_var.get())[1]
        if color:
            color_var.set(color)
            color_preview.config(bg=color)
            popup.focus()

    pick_btn = tk.Button(color_row, text="Pick Color",
                         font=("Segoe UI", label_fs, "bold"),
                         bg="#1E88E5", fg="white", bd=0,
                         padx=16, pady=6, cursor="hand2",
                         command=pick_color)
    pick_btn.pack(side="left")
    pick_btn.bind("<Enter>", lambda e: pick_btn.config(bg="#1565C0"))
    pick_btn.bind("<Leave>", lambda e: pick_btn.config(bg="#1E88E5"))

    _field_label("Operating Hours:")
    hours_entry = _entry()

    # Bottom padding
    tk.Frame(scroll_inner, bg="white", height=14).pack()

    # Pre fill when editing
    if is_edit:
        name_entry.insert(0, service['service_name'])
        code_entry.insert(0, service['service_code'])
        if service.get('color'):
            color_var.set(service['color'])
            color_preview.config(bg=service['color'])
        hours_entry.insert(0, service.get('operating_hours', 'Mon-Fri, 8AM-5PM'))
    else:
        hours_entry.insert(0, "Mon-Fri, 8AM-5PM")

    # Save logic
    def save_service():
        name  = name_entry.get().strip()
        code  = code_entry.get().strip().upper()
        color = color_var.get()
        hours = hours_entry.get().strip() or "Mon-Fri, 8AM-5PM"

        if not name or not code:
            messagebox.showerror("Error", "Service Name and Code are required", parent=popup)
            return

        api_endpoint = API_URL if API_URL.endswith('/api') else f"{API_URL}/api"

        try:
            if is_edit:
                response = requests.put(
                    f"{api_endpoint}/services/{service['service_id']}/update",
                    json={
                        'service_name':    name,
                        'service_code':    code,
                        'color':           color,
                        'operating_hours': hours,
                    },
                    timeout=REQUEST_TIMEOUT
                )
                if response.status_code == 200:
                    result = response.json()
                    if result.get('success'):
                        tickets_updated = result.get('tickets_updated', 0)
                        msg = f"{name} updated successfully!"
                        if tickets_updated > 0:
                            msg += f"\n\n{tickets_updated} existing ticket(s) updated with new code."
                        messagebox.showinfo("Success", msg, parent=popup)
                        popup.destroy()
                        load_opd_services(parent_frame)
                    else:
                        messagebox.showerror("Error",
                                             result.get('message', 'Failed to update service'),
                                             parent=popup)
                elif response.status_code == 409:
                    messagebox.showerror("Error",
                                         "That Service Code already exists. Choose a different one.",
                                         parent=popup)
                else:
                    messagebox.showerror("Error",
                                         f"Server error: {response.status_code}", parent=popup)
            else:
                response = requests.post(
                    f"{api_endpoint}/services/create",
                    json={
                        'service_name':    name,
                        'service_code':    code,
                        'color':           color,
                        'operating_hours': hours,
                    },
                    timeout=REQUEST_TIMEOUT
                )
                if response.status_code == 200:
                    result = response.json()
                    if result.get('success'):
                        messagebox.showinfo("Success", f"{name} created successfully!", parent=popup)
                        popup.destroy()
                        load_opd_services(parent_frame)
                    else:
                        messagebox.showerror("Error",
                                             result.get('message', 'Failed to create service'),
                                             parent=popup)
                elif response.status_code == 409:
                    messagebox.showerror("Error", "Service code already exists", parent=popup)
                else:
                    messagebox.showerror("Error",
                                         f"Server error: {response.status_code}", parent=popup)

        except requests.exceptions.ConnectionError:
            messagebox.showerror("Connection Error",
                f"Cannot connect to server at:\n{API_URL}\n\n"
                "Please check:\n"
                "1. Server is running (python main.py)\n"
                "2. Server laptop has IS_SERVER = True\n"
                "3. Both computers on same WiFi",
                parent=popup)
        except requests.exceptions.Timeout:
            messagebox.showerror("Timeout", "Server request timed out", parent=popup)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {str(e)}", parent=popup)

    tk.Frame(card, bg="#E0E0E0", height=1).pack(fill="x", padx=padx, pady=(0, 0))

    btn_bar = tk.Frame(card, bg="white")
    btn_bar.pack(fill="x", padx=padx, pady=14)

    def _action_btn(parent, text, bg, hover, cmd):
        b = tk.Button(parent, text=text,
                      font=("Segoe UI", btn_fs, "bold"),
                      bg=bg, fg="white",
                      bd=0, relief="flat", cursor="hand2",
                      padx=20, pady=12,
                      command=cmd)
        b.pack(side="left", fill="x", expand=True, padx=6)
        b.bind("<Enter>", lambda e: b.config(bg=hover))
        b.bind("<Leave>", lambda e: b.config(bg=bg))

    _action_btn(btn_bar, "✔  Confirm", "#43A047", "#2E7D32", save_service)
    _action_btn(btn_bar, "✕  Cancel",  "#E53935", "#B71C1C", popup.destroy)


# Delete Confirmation
def delete_service_popup(service_id, service_name, parent_frame):
    popup = tk.Toplevel()
    popup.title("Confirm Delete")

    screen_width  = popup.winfo_screenwidth()
    screen_height = popup.winfo_screenheight()

    popup_width  = min(380, int(screen_width  * 0.28))
    popup_height = min(185, int(screen_height * 0.23))

    popup.geometry(f"{popup_width}x{popup_height}")
    popup.configure(bg="#F4F6F8")
    popup.resizable(False, False)

    force_popup_to_parent_screen(popup, parent_frame)

    label_font_size  = max(11, min(12, int(popup_height * 0.080)))
    button_font_size = max(10, min(11, int(popup_height * 0.073)))
    label_pady       = max(15, min(20, int(popup_height * 0.133)))

    tk.Label(popup, text=f"Delete \"{service_name}\"?",
             font=("Segoe UI", label_font_size, "bold"), bg="#F4F6F8").pack(pady=(label_pady, 4))
    tk.Label(popup,
             text="This will permanently remove the service\nand cannot be undone.",
             font=("Segoe UI", 9), bg="#F4F6F8", fg="#E53935",
             justify="center").pack()

    def confirm_delete():
        try:
            api_endpoint = API_URL if API_URL.endswith('/api') else f"{API_URL}/api"
            response = requests.delete(
                f"{api_endpoint}/services/{service_id}/delete",
                timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    messagebox.showinfo("Deleted",
                                        f"\"{service_name}\" has been permanently deleted.",
                                        parent=popup)
                    popup.destroy()
                    load_opd_services(parent_frame)
                else:
                    messagebox.showerror("Error",
                                         result.get('message', 'Failed to delete service'),
                                         parent=popup)
            elif response.status_code == 400:
                result = response.json()
                messagebox.showerror("Cannot Delete",
                                     result.get('message', 'Service has existing tickets.'),
                                     parent=popup)
            else:
                messagebox.showerror("Error",
                                     f"Server error: {response.status_code}",
                                     parent=popup)
        except requests.exceptions.ConnectionError:
            messagebox.showerror("Connection Error",
                f"Cannot connect to server at:\n{API_URL}\n\n"
                "Please check:\n"
                "1. Server is running (python main.py)\n"
                "2. Server laptop has IS_SERVER = True\n"
                "3. Both computers on same WiFi",
                parent=popup)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete: {str(e)}", parent=popup)

    def styled_btn(parent, text, bg, fg, command):
        btn_padx = max(8,  min(10, int(popup_width  * 0.033)))
        btn_pady = max(6,  min(8,  int(popup_height * 0.053)))
        btn = tk.Button(parent, text=text,
                        font=("Segoe UI", button_font_size, "bold"),
                        bg=bg, fg=fg, bd=2, relief="ridge", cursor="hand2",
                        padx=btn_padx, pady=btn_pady, command=command)
        btn.pack(side="left", fill="x", expand=True, padx=5)
        hover = "#388E3C" if bg == "#43A047" else "#D32F2F"
        btn.bind("<Enter>", lambda e: btn.config(bg=hover))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg))
        return btn

    btn_frame_pady = max(8,  min(10, int(popup_height * 0.067)))
    btn_frame_padx = max(15, min(20, int(popup_width  * 0.067)))

    btn_frame = tk.Frame(popup, bg="#F4F6F8")
    btn_frame.pack(pady=btn_frame_pady, fill="x", padx=btn_frame_padx)
    styled_btn(btn_frame, "Yes, Delete", "#E53935", "white", confirm_delete)
    styled_btn(btn_frame, "Cancel",      "#757575", "white", popup.destroy)


# Load OPD Services from API
def load_opd_services(frame):
    for widget in frame.winfo_children():
        widget.destroy()

    frame.configure(bg="#F4F6F8")

    # Header
    header_frame = tk.Frame(frame, bg="white", bd=2, relief="ridge")
    header_frame.pack(fill="x", pady=10, padx=10)

    tk.Label(header_frame, text="OPD Services Management",
             font=("Segoe UI", 16, "bold"), bg="white").pack(side="left", padx=10, pady=10)

    add_btn = tk.Button(header_frame, text="+ Add Service",
                        font=("Segoe UI", 11, "bold"),
                        bg="#1E88E5", fg="white", bd=0, cursor="hand2",
                        command=lambda: add_service_popup(frame))
    add_btn.pack(side="right", padx=10, pady=10)
    add_btn.bind("<Enter>", lambda e: add_btn.config(bg="#1565C0"))
    add_btn.bind("<Leave>", lambda e: add_btn.config(bg="#1E88E5"))

    # Table Frame
    table_frame = tk.Frame(frame, bg="white", bd=2, relief="ridge")
    table_frame.pack(fill="both", expand=True, padx=10, pady=10)

    # Actions column
    columns = ("Color", "Service Name", "Code", "Operating Hours", "Status", "Actions")
    tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=15)
    tree.pack(fill="both", expand=True, padx=5, pady=5)

    tree.column("Color",           width=60,  anchor="center")
    tree.column("Service Name",    width=200, anchor="center")
    tree.column("Code",            width=100, anchor="center")
    tree.column("Operating Hours", width=180, anchor="center")
    tree.column("Status",          width=120, anchor="center")
    tree.column("Actions",         width=180, anchor="center")

    for col in columns:
        tree.heading(col, text=col)

    # Loading label
    loading_lbl = tk.Label(table_frame,
                           text="⏳  Loading services…",
                           font=("Segoe UI", 11, "italic"),
                           bg="white", fg="#9E9E9E")
    loading_lbl.place(relx=0.5, rely=0.5, anchor="center")

    widget_refs = []
    service_map = {}

    # redraw
    def redraw():
        tree.update_idletasks()
        for w in widget_refs:
            try:
                w.destroy()
            except Exception:
                pass
        widget_refs.clear()

        for sid, srv in service_map.items():

            # Color swatch
            bbox = tree.bbox(sid, column="Color")
            if bbox:
                x, y, width, height = bbox
                canvas = tk.Canvas(tree, width=20, height=height - 6,
                                   bg=srv.get('color', '#1E88E5'),
                                   highlightthickness=1,
                                   highlightbackground="#B0BEC5")
                canvas.place(x=x + (width // 2 - 10), y=y + 3)
                widget_refs.append(canvas)

            # Status toggle
            bbox = tree.bbox(sid, column="Status")
            if not bbox:
                continue

            active    = (srv.get('is_active', 1) == 1)
            col_width = bbox[2]

            toggle = tk.Label(tree,
                              text="ON" if active else "OFF",
                              bg="#4CAF50" if active else "#9E9E9E",
                              fg="white",
                              font=("Segoe UI", 9, "bold"),
                              cursor="hand2", padx=8, pady=2, bd=1, relief="solid")
            toggle.update_idletasks()
            toggle_width = toggle.winfo_reqwidth()
            toggle.place(x=bbox[0] + (col_width - toggle_width) // 2 - 30, y=bbox[1] + 6)
            widget_refs.append(toggle)

            status_label = tk.Label(tree,
                                    text="Active" if active else "Inactive",
                                    font=("Segoe UI", 9),
                                    bg="white", fg="#263238")
            status_label.update_idletasks()
            label_width = status_label.winfo_reqwidth()
            status_label.place(x=bbox[0] + (col_width - label_width) // 2 + 30,
                               y=bbox[1] + 6)
            widget_refs.append(status_label)

            def make_toggle_handler(service_id):
                def toggle_status(event=None):
                    try:
                        api_ep = API_URL if API_URL.endswith('/api') else f"{API_URL}/api"
                        r = requests.put(f"{api_ep}/services/{service_id}/toggle",
                                         timeout=REQUEST_TIMEOUT)
                        if r.status_code == 200:
                            load_opd_services(frame)
                        else:
                            messagebox.showerror("Error", "Failed to toggle service status")
                    except Exception as ex:
                        messagebox.showerror("Error", f"Failed to toggle: {str(ex)}")
                return toggle_status

            toggle.bind("<Button-1>", make_toggle_handler(sid))
            status_label.bind("<Button-1>", make_toggle_handler(sid))

            # Edit and Delete buttons
            act_bbox = tree.bbox(sid, column="Actions")
            if not act_bbox:
                continue

            ax, ay, aw, ah = act_bbox
            btn_w   = 66
            gap     = 8
            total_w = btn_w * 2 + gap
            start_x = ax + (aw - total_w) // 2
            btn_h   = max(22, ah - 8)

            # Edit
            edit_btn = tk.Button(
                tree,
                text="✏  Edit",
                font=("Segoe UI", 8, "bold"),
                bg="#43A047", fg="white",
                bd=0, relief="flat", cursor="hand2",
                command=lambda s=srv: add_service_popup(frame, s)
            )
            edit_btn.place(x=start_x, y=ay + 4, width=btn_w, height=btn_h)
            edit_btn.bind("<Enter>", lambda e, b=edit_btn: b.config(bg="#2E7D32"))
            edit_btn.bind("<Leave>", lambda e, b=edit_btn: b.config(bg="#43A047"))
            widget_refs.append(edit_btn)

            # Delete
            del_btn = tk.Button(
                tree,
                text="🗑  Delete",
                font=("Segoe UI", 8, "bold"),
                bg="#E53935", fg="white",
                bd=0, relief="flat", cursor="hand2",
                command=lambda i=sid, n=srv['service_name']: delete_service_popup(i, n, frame)
            )
            del_btn.place(x=start_x + btn_w + gap, y=ay + 4, width=btn_w, height=btn_h)
            del_btn.bind("<Enter>", lambda e, b=del_btn: b.config(bg="#B71C1C"))
            del_btn.bind("<Leave>", lambda e, b=del_btn: b.config(bg="#E53935"))
            widget_refs.append(del_btn)

    # Edit/Delete
    tree.bind("<Button-1>", lambda e: None)

    def _fetch():
        try:
            api_endpoint = API_URL if API_URL.endswith('/api') else f"{API_URL}/api"
            print(f"[OPD SERVICES] Fetching from: {api_endpoint}/services/list")
            response = requests.get(f"{api_endpoint}/services/list", timeout=REQUEST_TIMEOUT)

            if response.status_code == 200:
                result   = response.json()
                services = result.get('services', []) if result.get('success') else []
            else:
                services = []
                frame.after(0, lambda: messagebox.showerror(
                    "Server Error", f"Error {response.status_code}"))

        except requests.exceptions.ConnectionError:
            services = []
            frame.after(0, lambda: messagebox.showerror("Connection Error",
                f"Cannot connect to server at:\n{API_URL}\n\n"
                "Please check:\n"
                "1. Server is running (python main.py)\n"
                "2. Server laptop has IS_SERVER = True\n"
                "3. Both computers on same WiFi"))
        except Exception as e:
            services = []
            frame.after(0, lambda msg=str(e): messagebox.showerror(
                "Error", f"Failed to load services: {msg}"))

        frame.after(0, lambda: _apply(services))

    def _apply(services):
        # Remove loading label
        try:
            loading_lbl.destroy()
        except Exception:
            pass

        if not services:
            tk.Label(table_frame,
                     text="No services available. Click '+ Add Service' to create one.",
                     font=("Segoe UI", 12), bg="white", fg="#999").pack(pady=50)
            return

        service_map.clear()
        service_map.update({s['service_id']: s for s in services})

        for sid, srv in service_map.items():
            tree.insert("", "end", iid=sid, values=(
                "",
                srv['service_name'],
                srv['service_code'],
                srv.get('operating_hours', 'Mon-Fri, 8AM-5PM'),
                "",
                "" 
            ))

        tree.after(200, redraw)

    threading.Thread(target=_fetch, daemon=True).start()