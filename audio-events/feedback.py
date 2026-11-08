"""Small local feedback window, separate from the settings editor."""

import sys
import tkinter as tk


class FeedbackPopup:
    def __init__(self, root):
        self.root = root
        self.window = None
        self.dismiss_timer = None
        self.session_id = None
        self.dismissed = None

    def update(self, update):
        session_id = update["session_id"]
        if update.get("action_result") and self.session_id != session_id:
            return
        if self.dismissed == session_id:
            return
        if session_id != self.session_id:
            self.hide()
            self.session_id = session_id
        if self.dismiss_timer:
            self.root.after_cancel(self.dismiss_timer)
            self.dismiss_timer = None
        if self.window is None:
            self._create()
        phase = update["phase"]
        self.heading.set({"listening": "Listening…", "running": "Running action…",
                          "complete": "Event received", "cancelled": "Cancelled"}[phase])
        self.phrase.set(update["phrase"])
        self.input.set(update["input"] or ("What would you like to say?" if phase == "listening" else "No input heard"))
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", self.input.get())
        if update.get("response"):
            self.text.insert("end", "\n\n" + update["response"])
        self.text.see("end")
        self.text.configure(state="disabled")
        self.details.set(update["event"] if phase == "complete" else "Offline · audio stays on this computer")
        if phase in ("complete", "cancelled"):
            self.dismiss_timer = self.root.after(int(update["cooldown_seconds"] * 1000), self.hide)

    def _create(self):
        window = self.window = tk.Toplevel(self.root)
        window.withdraw()
        window.title("Bobo · Voice feedback")
        window.configure(bg="#142c3a")
        window.resizable(False, False)
        window.attributes("-topmost", True)
        window.overrideredirect(True)
        width, height = 520, 280
        x = (window.winfo_screenwidth() - width) // 2
        y = max(20, window.winfo_screenheight() - height - 85)
        window.geometry(f"{width}x{height}+{x}+{y}")
        self.heading = tk.StringVar()
        self.phrase = tk.StringVar()
        self.input = tk.StringVar()
        self.details = tk.StringVar()
        top = tk.Frame(window, bg="#142c3a")
        top.pack(fill="x", padx=22, pady=(16, 0))
        tk.Label(top, text="●  BOBO", bg="#142c3a", fg="#83ded3", font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Button(top, text="×", command=self.dismiss, bg="#142c3a", fg="#c8d8e2", relief="flat",
                  borderwidth=0, font=("Segoe UI", 14), cursor="hand2").pack(side="right")
        tk.Label(window, textvariable=self.heading, bg="#142c3a", fg="white", font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=22)
        tk.Label(window, textvariable=self.phrase, bg="#142c3a", fg="#83ded3", font=("Segoe UI", 10)).pack(anchor="w", padx=22, pady=(3, 8))
        self.text = tk.Text(window, bg="#142c3a", fg="white", wrap="word", height=4,
                            relief="flat", takefocus=False, font=("Segoe UI", 12), state="disabled")
        self.text.pack(fill="both", expand=True, padx=22)
        tk.Label(window, textvariable=self.details, bg="#142c3a", fg="#b1c8d7", font=("Segoe UI", 9)).pack(anchor="w", padx=22, pady=(8, 15))
        window.bind("<Escape>", lambda _: self.dismiss())
        if sys.platform == "win32":
            import ctypes
            window.update_idletasks()
            user32 = ctypes.windll.user32
            handle = user32.GetParent(window.winfo_id())
            extended = user32.GetWindowLongW(handle, -20)
            user32.SetWindowLongW(handle, -20, extended | 0x08000000 | 0x80)
            user32.SetWindowPos(handle, -1, 0, 0, 0, 0, 0x0013)
        window.deiconify()

    def dismiss(self):
        self.dismissed = self.session_id
        self.hide()

    def hide(self):
        if self.dismiss_timer:
            self.root.after_cancel(self.dismiss_timer)
            self.dismiss_timer = None
        if self.window:
            self.window.destroy()
            self.window = None
