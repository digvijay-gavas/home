"""Draggable, translucent desktop control for the offline Bobo listener."""

import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import sys
import time
import tkinter as tk
from tkinter import messagebox

from runtime import AlreadyRunning, claim_listener, listener_running, send_signal

ROOT = Path(__file__).resolve().parent


class FloatingControl:
    def __init__(self, root, config_path):
        self.root = root
        self.config = config_path.resolve()
        self.position_file = self.config.with_suffix(".controls.json")
        self.child = None
        self.closing = False
        self.dragged = False
        self.running = False
        self.starting = False
        self.pending_tab = None
        self.settings_child = None
        self.quit_deadline = 0
        root.title("Bobo · Floating control")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.86)
        root.configure(bg="#ff00ff")
        root.attributes("-transparentcolor", "#ff00ff")
        root.geometry("68x68")
        self.canvas = tk.Canvas(root, width=68, height=68, bg="#ff00ff", highlightthickness=0, cursor="hand2")
        self.canvas.pack()
        self.canvas.create_oval(3, 3, 65, 65, fill="#173749", outline="#80d7ce", width=2)
        self.canvas.create_text(34, 31, text="B", fill="white", font=("Segoe UI", 25, "bold"))
        self.dot = self.canvas.create_oval(47, 48, 61, 62, fill="#e2a756", outline="#173749", width=2)
        self.menu = tk.Menu(root, tearoff=False, font=("Segoe UI", 10))
        self.menu.add_command(label="Listener off", state="disabled")
        self.menu.add_separator()
        self.menu.add_command(label="Start listener", command=self.start)
        self.menu.add_command(label="Stop listener", command=self.stop)
        self.menu.add_separator()
        self.menu.add_command(label="Settings", command=lambda: self.open_settings("settings"))
        self.menu.add_command(label="Event log", command=lambda: self.open_settings("event_log"))
        self.menu.add_separator()
        self.menu.add_command(label="Quit Bobo (stop listener)", command=self.quit)
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<Button-3>", self.show_menu)
        root.protocol("WM_DELETE_WINDOW", self.quit)
        root.update_idletasks()
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.GetParent.argtypes = (wintypes.HWND,)
        self.user32.GetParent.restype = wintypes.HWND
        self.user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
        self.user32.SetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_long)
        self.user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                             ctypes.c_int, ctypes.c_int, wintypes.UINT)
        self.handle = self.user32.GetParent(root.winfo_id())
        # Keep a normal application identity while the visible control remains
        # borderless; it can also be recovered from the Windows taskbar.
        extended_style = self.user32.GetWindowLongW(self.handle, -20)
        self.user32.SetWindowLongW(self.handle, -20, (extended_style & ~0x80) | 0x40000)
        x, y = root.winfo_screenwidth() - 105, 120
        try:
            saved = json.loads(self.position_file.read_text(encoding="utf-8"))
            x, y = int(saved["x"]), int(saved["y"])
        except (OSError, ValueError, TypeError, KeyError):
            pass
        left, top = self.user32.GetSystemMetrics(76), self.user32.GetSystemMetrics(77)
        width, height = self.user32.GetSystemMetrics(78), self.user32.GetSystemMetrics(79)
        self.move(max(left, min(x, left + width - 68)), max(top, min(y, top + height - 68)))
        self.poll()

    def move(self, x, y):
        self.user32.SetWindowPos(self.handle, None, int(x), int(y), 0, 0, 0x0015)

    def press(self, event):
        self.anchor = (event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y())
        self.dragged = False

    def drag(self, event):
        mouse_x, mouse_y, x, y = self.anchor
        dx, dy = event.x_root - mouse_x, event.y_root - mouse_y
        if abs(dx) + abs(dy) > 4:
            self.dragged = True
        if self.dragged:
            self.move(x + dx, y + dy)

    def release(self, event):
        if self.dragged:
            self.save_position()
        else:
            self.show_menu(event)

    def save_position(self):
        try:
            self.position_file.write_text(json.dumps({"x": self.root.winfo_x(), "y": self.root.winfo_y()}), encoding="utf-8")
        except OSError:
            pass

    def show_menu(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def start(self):
        if self.running or self.starting:
            return
        python = Path(sys.executable).with_name("pythonw.exe")
        self.child = subprocess.Popen([str(python), str(ROOT / "runtime.py"), "--config", str(self.config)],
                                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
        self.starting = True
        self.refresh_status()

    def stop(self):
        send_signal(self.config, "stop")

    def open_settings(self, tab):
        if send_signal(self.config, tab):
            return
        self.pending_tab = tab
        if self.settings_child and self.settings_child.poll() is None:
            return
        python = Path(sys.executable).with_name("pythonw.exe")
        self.settings_child = subprocess.Popen([str(python), str(ROOT / "ui.py"), "--config", str(self.config), "--tab", tab],
                                               creationflags=subprocess.CREATE_NO_WINDOW)

    def refresh_status(self):
        self.running = bool(listener_running(self.config))
        if self.running:
            self.starting = False
        if self.child and self.child.poll() is not None:
            self.child = None
            self.starting = False
        label = "Listener running" if self.running else "Starting…" if self.starting else "Listener off"
        self.canvas.itemconfigure(self.dot, fill="#63dfaa" if self.running else "#e2a756")
        self.menu.entryconfigure(0, label=label)
        self.menu.entryconfigure(2, state="disabled" if self.running or self.starting else "normal")
        self.menu.entryconfigure(3, state="normal" if self.running else "disabled")

    def poll(self):
        try:
            self.refresh_status()
            if self.pending_tab and send_signal(self.config, self.pending_tab):
                self.pending_tab = None
            if self.closing:
                if not self.running and not self.starting:
                    self.save_position()
                    self.root.destroy()
                    return
                self.stop()
                if time.monotonic() > self.quit_deadline:
                    self.closing = False
                    messagebox.showinfo("Listener still running", "The listener has not stopped yet. Dismiss any listener error dialog and try Stop again.", parent=self.root)
        except Exception as error:
            self.menu.entryconfigure(0, label="Control error: " + str(error)[:60])
        self.root.after(250, self.poll)

    def quit(self):
        self.closing = True
        self.quit_deadline = time.monotonic() + 10
        self.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("The floating control currently supports Windows only")
    try:
        claim = claim_listener(args.config, "controls")
    except AlreadyRunning:
        return
    root = tk.Tk()
    try:
        FloatingControl(root, args.config)
        root.mainloop()
    finally:
        claim[0].CloseHandle(claim[1])


if __name__ == "__main__":
    main()
