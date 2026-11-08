"""Settings editor only. Listening and transient feedback run separately."""

import argparse
import copy
from datetime import datetime
import json
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
import uuid

from configuration import read_config, save_config, validate_config
from feedback import FeedbackPopup
from event_log import EventLog, log_path
from runtime import AlreadyRunning, LocalSignal, claim_listener, listener_running, send_signal

ROOT = Path(__file__).resolve().parent
DEFAULTS = {"id": "", "phrase": "", "event": "voice_command.received", "min_confidence": 0.8,
            "cooldown_seconds": 2.0, "argument_timeout_seconds": 5.0, "silence_seconds": 1.2,
            "max_argument_seconds": 15.0, "capture_arguments": True, "show_feedback": True}
BOOL_FIELDS = ("capture_arguments", "show_feedback")
NUMBER_FIELDS = ("min_confidence", "cooldown_seconds", "argument_timeout_seconds", "silence_seconds", "max_argument_seconds")


class AudioEventsApp:
    def __init__(self, root, config_path):
        self.root = root
        self.config_path = Path(config_path).resolve()
        self.config = read_config(self.config_path)
        self.selected_id = None
        self.dirty = False
        self.saving = False
        self.closed = False
        self.mailbox = queue.Queue()
        self.history = EventLog(log_path(self.config_path))
        self.history_events = {}
        self.history_ids = []
        self.navigation_signals = {}
        self.next_history_check = 0
        self.history_note = tk.StringVar()
        self.service_status = tk.StringVar(value="Checking desktop listener…")
        self.fields = {key: tk.BooleanVar() if key in BOOL_FIELDS else tk.StringVar() for key in DEFAULTS}
        self.notice = tk.StringVar(value="Changes are saved locally. A running listener reloads trigger changes automatically.")
        self.popup = FeedbackPopup(root)
        self._build()
        self._refresh()
        self._select(self.config["triggers"][0]["id"])
        for variable in self.fields.values():
            variable.trace_add("write", self._mark_dirty)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self._poll)

    def _build(self):
        root = self.root
        root.title("Bobo · Settings & event log")
        root.geometry("1060x820")
        root.minsize(990, 780)
        root.configure(bg="#f2f5f7")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#f2f5f7")
        style.configure("TLabel", background="#f2f5f7", foreground="#203343", font=("Segoe UI", 10))
        style.configure("TCheckbutton", background="#f2f5f7", font=("Segoe UI", 10))
        style.configure("TButton", padding=(12, 7), font=("Segoe UI", 10))
        style.configure("Accent.TButton", background="#087f78", foreground="white")
        style.map("Accent.TButton", background=[("active", "#096b66"), ("disabled", "#809995")])
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=32)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), padding=7)
        style.map("Treeview", background=[("selected", "#d5eeeb")], foreground=[("selected", "#153d39")])
        header = tk.Frame(root, bg="#172d3b", padx=24, pady=18)
        header.pack(fill="x")
        tk.Label(header, text="BOBO / SETTINGS", bg="#172d3b", fg="#7edacf", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(header, text="Make it listen your way.", bg="#172d3b", fg="white", font=("Segoe UI", 22, "bold")).pack(anchor="w", pady=4)
        tk.Label(header, text="Settings and local event history. Your listener runs separately. Everything stays offline.",
                 bg="#172d3b", fg="#c5d8e3", font=("Segoe UI", 10)).pack(anchor="w")
        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True)
        body = ttk.Frame(self.tabs, padding=22)
        self.tabs.add(body, text="Trigger settings")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 22))
        ttk.Label(left, text="Your triggers", font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 10))
        self.triggers = ttk.Treeview(left, columns=("phrase", "event"), show="headings", height=6, selectmode="browse")
        for key, label in (("phrase", "Say this"), ("event", "Emit this event")):
            self.triggers.heading(key, text=label)
            self.triggers.column(key, width=180, minwidth=120)
        self.triggers.pack(fill="both", expand=True)
        self.triggers.bind("<<TreeviewSelect>>", self._on_select)
        controls = ttk.Frame(left)
        controls.pack(fill="x", pady=12)
        self.buttons = []
        for text, command in (("+ New", self.new), ("Delete", self.delete), ("Reload", self.reload)):
            button = ttk.Button(controls, text=text, command=command)
            button.pack(side="left", padx=(0, 6))
            self.buttons.append(button)
        ttk.Label(left, text="Start listening with start.bat.\nClosing settings does not stop the listener.\n\nFeedback appears only for triggers with\n“Show feedback popup” enabled.",
                  justify="left").pack(anchor="w", pady=(5, 0))

        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(1, weight=1)
        self.entries = []
        for index, (key, label) in enumerate([
            ("phrase", "Wake phrase"), ("event", "Event name"), ("id", "Trigger ID"),
            ("min_confidence", "Confidence (0–1)"), ("cooldown_seconds", "Cooldown / popup hold (s)"),
            ("argument_timeout_seconds", "Wait for input (s)"), ("silence_seconds", "End after silence (s)"),
            ("max_argument_seconds", "Maximum capture (s)")]):
            ttk.Label(right, text=label).grid(row=index, column=0, sticky="w", padx=(0, 10), pady=6)
            entry = ttk.Entry(right, textvariable=self.fields[key], font=("Segoe UI", 10))
            entry.grid(row=index, column=1, sticky="ew", pady=6)
            self.entries.append(entry)
        for index, (key, label) in enumerate((("capture_arguments", "Capture speech after this phrase"),
                                               ("show_feedback", "Show feedback popup")), start=8):
            check = ttk.Checkbutton(right, text=label, variable=self.fields[key])
            check.grid(row=index, column=0, columnspan=2, sticky="w", pady=7)
            self.entries.append(check)
        save = ttk.Button(right, text="Save trigger", style="Accent.TButton", command=self.save)
        save.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(12, 7))
        preview = ttk.Button(right, text="Preview feedback", command=self.preview)
        preview.grid(row=11, column=0, columnspan=2, sticky="ew")
        self.buttons.extend((save, preview))
        ttk.Label(body, textvariable=self.notice, wraplength=990).grid(row=1, column=0, columnspan=2, sticky="w", pady=(16, 0))
        self._build_history()

    def _build_history(self):
        tab = ttk.Frame(self.tabs, padding=22)
        self.tabs.add(tab, text="Event log")
        top = ttk.Frame(tab)
        top.pack(fill="x", pady=(0, 12))
        ttk.Label(top, textvariable=self.service_status, font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(top, text="Clear history", command=self.clear_history).pack(side="right")
        ttk.Button(top, text="Refresh", command=lambda: self._refresh_history(force=True)).pack(side="right", padx=8)
        ttk.Label(tab, text="Completed microphone events · latest 200 shown · 1,000 retained locally").pack(anchor="w", pady=(0, 8))
        table = ttk.Frame(tab)
        table.pack(fill="both", expand=True)
        self.event_table = ttk.Treeview(table, columns=("time", "event", "phrase", "input"), show="headings", selectmode="browse", height=8)
        for key, title, width in (("time", "Time", 150), ("event", "Event", 230),
                                  ("phrase", "Wake phrase", 160), ("input", "Captured input", 390)):
            self.event_table.heading(key, text=title)
            self.event_table.column(key, width=width, minwidth=90)
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.event_table.yview)
        self.event_table.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.event_table.pack(side="left", fill="both", expand=True)
        self.event_table.bind("<<TreeviewSelect>>", self._show_event)
        ttk.Label(tab, text="Selected event", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(12, 4))
        self.event_details = tk.Text(tab, height=7, wrap="word", font=("Consolas", 10),
                                     bg="#e7edf1", fg="#203343", relief="flat", state="disabled")
        self.event_details.pack(fill="x")
        ttk.Label(tab, textvariable=self.history_note, wraplength=990).pack(anchor="w", pady=(10, 0))
        self._refresh_history(force=True)

    def _show_event(self, _=None):
        selection = self.event_table.selection()
        event = self.history_events.get(selection[0]) if selection else None
        self.event_details.configure(state="normal")
        self.event_details.delete("1.0", "end")
        if event:
            self.event_details.insert("1.0", json.dumps(event, indent=2, ensure_ascii=False))
        self.event_details.configure(state="disabled")

    def _refresh_history(self, force=False):
        self.next_history_check = time.monotonic() + 1
        try:
            running = listener_running(self.config_path)
            self.service_status.set("Desktop listener running" if running else
                                    "Desktop listener off · open start.bat to listen" if running is False else
                                    "Desktop listener status unavailable")
            events = self.history.latest()
            ids = [event["id"] for event in events]
            if force or ids != self.history_ids:
                selected = self.event_table.selection()
                self.history_events = {event["id"]: event for event in events}
                self.history_ids = ids
                self.event_table.delete(*self.event_table.get_children())
                for event in events:
                    try:
                        timestamp = datetime.fromisoformat(event["timestamp"]).astimezone().strftime("%d %b %H:%M:%S")
                    except (ValueError, KeyError):
                        timestamp = event.get("timestamp", "")
                    self.event_table.insert("", "end", iid=event["id"], values=(timestamp, event.get("type", ""),
                                            event.get("phrase", ""), event.get("input", "")))
                if ids:
                    self.event_table.selection_set(selected[0] if selected and selected[0] in ids else ids[0])
                self._show_event()
            prefix = f"{len(events)} events shown." if events else "No events yet. Start the listener, then say a wake phrase."
            self.history_note.set(prefix + " Stored only on this computer: " + str(self.history.path))
        except Exception as error:
            self.history_note.set("Could not refresh event history: " + str(error))

    def clear_history(self):
        if messagebox.askyesno("Clear local history", "Delete the locally saved event history, including captured input?", parent=self.root):
            try:
                self.history.clear()
                self._refresh_history(force=True)
            except Exception as error:
                messagebox.showerror("Cannot clear history", str(error), parent=self.root)

    def _mark_dirty(self, *_):
        self.dirty = True

    def _refresh(self):
        self.triggers.delete(*self.triggers.get_children())
        for trigger in self.config["triggers"]:
            self.triggers.insert("", "end", iid=trigger["id"], values=(trigger["phrase"], trigger["event"]))

    def _select(self, trigger_id):
        self.triggers.selection_set(trigger_id)
        self.triggers.see(trigger_id)
        self._load(trigger_id)

    def _load(self, trigger_id):
        trigger = next(t for t in self.config["triggers"] if t["id"] == trigger_id)
        self.selected_id = trigger_id
        for key, variable in self.fields.items():
            # Existing phrase-only triggers stay phrase-only until explicitly enabled.
            value = trigger.get(key, False if key in BOOL_FIELDS else DEFAULTS[key])
            variable.set(value if key in BOOL_FIELDS else str(value))
        self.dirty = False

    def _discard_edits(self):
        return not self.dirty or messagebox.askyesno("Unsaved edits", "Discard unsaved trigger edits?", parent=self.root)

    def _on_select(self, _):
        selection = self.triggers.selection()
        if self.saving or not selection or selection[0] == self.selected_id:
            return
        if self._discard_edits():
            self._load(selection[0])
        elif self.selected_id:
            self.triggers.selection_set(self.selected_id)
        else:
            self.triggers.selection_remove(*selection)

    def new(self):
        if self.saving or not self._discard_edits():
            return
        self.selected_id = None
        self.triggers.selection_remove(*self.triggers.selection())
        for key, value in DEFAULTS.items():
            self.fields[key].set(value if key in BOOL_FIELDS else str(value))
        self.dirty = False
        self.entries[0].focus_set()

    def _form(self):
        trigger = next((copy.deepcopy(t) for t in self.config["triggers"] if t["id"] == self.selected_id), {})
        for key, variable in self.fields.items():
            trigger[key] = variable.get() if key in BOOL_FIELDS else variable.get().strip()
        for key in NUMBER_FIELDS:
            trigger[key] = float(trigger[key])
        return trigger

    def save(self):
        if self.saving:
            return
        try:
            trigger = self._form()
            candidate = copy.deepcopy(self.config)
            if self.selected_id is None:
                candidate["triggers"].append(trigger)
            else:
                index = next(i for i, t in enumerate(candidate["triggers"]) if t["id"] == self.selected_id)
                candidate["triggers"][index] = trigger
            validate_config(candidate)
        except (ValueError, TypeError) as error:
            messagebox.showerror("Cannot save trigger", str(error), parent=self.root)
            return
        self._validate_and_save(candidate, trigger["id"])

    def delete(self):
        if self.saving or self.selected_id is None or not self._discard_edits():
            return
        if len(self.config["triggers"]) == 1:
            messagebox.showinfo("Keep one trigger", "Add another trigger before deleting this one.", parent=self.root)
            return
        if messagebox.askyesno("Delete trigger", "Delete the selected trigger?", parent=self.root):
            candidate = copy.deepcopy(self.config)
            candidate["triggers"] = [t for t in candidate["triggers"] if t["id"] != self.selected_id]
            self._validate_and_save(candidate, candidate["triggers"][0]["id"])

    def reload(self):
        if self.saving or not self._discard_edits():
            return
        try:
            self.config = read_config(self.config_path)
            self._refresh()
            self._select(self.config["triggers"][0]["id"])
        except Exception as error:
            messagebox.showerror("Cannot reload settings", str(error), parent=self.root)

    def preview(self):
        try:
            trigger = self._form()
            candidate = dict(self.config, triggers=[trigger])
            validate_config(candidate)
            self.popup.update({"phase": "complete", "session_id": str(uuid.uuid4()), "phrase": trigger["phrase"],
                               "event": trigger["event"], "input": "what is the time now", "cooldown_seconds": trigger["cooldown_seconds"]})
        except (ValueError, TypeError) as error:
            messagebox.showerror("Cannot preview", str(error), parent=self.root)

    def _busy(self, busy):
        self.saving = busy
        for widget in self.buttons + self.entries:
            widget.configure(state="disabled" if busy else "normal")

    def _validate_and_save(self, candidate, selection):
        self._busy(True)
        self.notice.set("Checking phrases against the installed offline model…")

        def validate():
            try:
                with tempfile.TemporaryDirectory(prefix="bobo-config-") as temporary:
                    path = Path(temporary) / "config.json"
                    check = copy.deepcopy(candidate)
                    check["model_path"] = str(self.config_path.parent / candidate["model_path"])
                    path.write_text(json.dumps(check), encoding="utf-8")
                    result = subprocess.run([sys.executable, str(ROOT / "listener.py"), "--config", str(path), "--validate-config"],
                                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=30)
                    if result.returncode:
                        raise ValueError(result.stderr.strip() or "Model validation failed")
                self.mailbox.put((candidate, selection, None))
            except Exception as error:
                self.mailbox.put((None, None, str(error)))

        threading.Thread(target=validate, daemon=True).start()

    def _poll(self):
        for name, signal in self.navigation_signals.items():
            if signal.received():
                self.tabs.select(1 if name == "event_log" else 0)
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
        if time.monotonic() >= self.next_history_check:
            self._refresh_history()
        try:
            candidate, selection, error = self.mailbox.get_nowait()
        except queue.Empty:
            pass
        else:
            try:
                if error:
                    raise ValueError(error)
                save_config(self.config_path, candidate)
                self.config = candidate
                self.selected_id = selection
                self.dirty = False
                self._refresh()
                self._select(selection)
                self.notice.set("Saved locally. A running listener reloads these triggers within a second.")
            except Exception as error:
                self.notice.set("Nothing was changed. Correct the trigger and try again.")
                messagebox.showerror("Cannot save settings", str(error), parent=self.root)
            finally:
                self._busy(False)
        if not self.closed:
            self.root.after(100, self._poll)

    def close(self):
        if self._discard_edits():
            self.closed = True
            self.popup.hide()
            self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--tab", choices=("settings", "event_log"), default="settings")
    args = parser.parse_args()
    claim = None
    if sys.platform == "win32":
        try:
            claim = claim_listener(args.config, "settings")
        except AlreadyRunning:
            # Reuse the existing settings window, including its unsaved form.
            import time
            for _ in range(20):
                if send_signal(args.config, args.tab):
                    return 0
                time.sleep(0.1)
            return 1
    root = tk.Tk()
    app = None
    try:
        app = AudioEventsApp(root, args.config)
        app.tabs.select(1 if args.tab == "event_log" else 0)
        if sys.platform == "win32":
            app.navigation_signals = {name: LocalSignal(args.config, name) for name in ("settings", "event_log")}
    except Exception as error:
        root.withdraw()
        messagebox.showerror("Cannot open settings", str(error), parent=root)
        root.destroy()
        if claim:
            claim[0].CloseHandle(claim[1])
        return 1
    try:
        root.mainloop()
    finally:
        for signal in app.navigation_signals.values():
            signal.close()
        if claim:
            claim[0].CloseHandle(claim[1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
