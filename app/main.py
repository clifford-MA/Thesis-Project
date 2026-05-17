import tkinter as tk

root = tk.Tk()
root.title("Tkinter Test - VS Code")
root.geometry("300x150")

label = tk.Label(root, text="Tkinter is working!")
label.pack(expand=True)

root.mainloop()
