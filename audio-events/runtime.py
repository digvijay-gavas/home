"""Listener runtime: no settings window, only opt-in event feedback."""

import queue
import signal
import sys
import threading
import tkinter as tk
from tkinter import messagebox

import listener
from feedback import FeedbackPopup


def mutex_name(config_path):
    import hashlib
    key = hashlib.sha256(str(config_path.resolve()).lower().encode()).hexdigest()
    return "Local\\BoboAudio_" + key


class AlreadyRunning(ValueError):
    pass


class LocalSignal:
    """Windows event used only for local process control; no network transport."""
    def __init__(self, config_path, kind):
        import ctypes
        from ctypes import wintypes
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateEventW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR)
        self.kernel.CreateEventW.restype = wintypes.HANDLE
        self.kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        self.kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.handle = self.kernel.CreateEventW(None, False, False, mutex_name(config_path) + "_signal_" + kind)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def received(self):
        import ctypes
        result = self.kernel.WaitForSingleObject(self.handle, 0)
        if result == 0:
            return True
        if result == 258:
            return False
        raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        self.kernel.CloseHandle(self.handle)


def send_signal(config_path, kind):
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenEventW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.OpenEventW.restype = wintypes.HANDLE
    kernel.SetEvent.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenEventW(2, False, mutex_name(config_path) + "_signal_" + kind)
    if not handle:
        if ctypes.get_last_error() == 2:
            return False
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not kernel.SetEvent(handle):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(handle)
    return True


def listener_running(config_path):
    """Inspect the desktop runtime without opening a microphone or a socket."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenMutexW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.OpenMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenMutexW(0x00100000, False, mutex_name(config_path))
    if handle:
        kernel.CloseHandle(handle)
        return True
    error = ctypes.get_last_error()
    if error == 2:
        return False
    if error == 5:
        return True
    raise ctypes.WinError(error)


def claim_listener(config_path, kind="listener"):
    """One microphone runtime per config in the current Windows session."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    name = mutex_name(config_path) + ("_" + kind if kind != "listener" else "")
    handle = kernel.CreateMutexW(None, False, name)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(handle)
        raise AlreadyRunning(f"Bobo {kind} is already running for this config.")
    return kernel, handle


def main():
    args = listener.parse_args()
    if args.check or args.validate_config or args.list_devices:
        return listener.main(args=args)
    root = tk.Tk()
    root.withdraw()
    claim = None
    stop_signal = None
    try:
        if not args.wav:
            claim = claim_listener(args.config)
            stop_signal = LocalSignal(args.config, "stop")
    except Exception as error:
        messagebox.showerror("Cannot start Bobo", str(error), parent=root)
        root.destroy()
        return 1
    updates = queue.Queue(maxsize=200)
    stopped = threading.Event()
    popup = FeedbackPopup(root)
    exit_code = 0

    def feedback(update):
        try:
            updates.put_nowait(("feedback", update))
        except queue.Full:
            if update["phase"] != "listening":
                updates.put(("feedback", update))

    def run():
        try:
            listener.main(feedback, stopped, args)
        except Exception as error:
            updates.put(("error", str(error)))
        finally:
            updates.put(("done", None))

    def stop(*_):
        stopped.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    def poll():
        nonlocal exit_code
        if stop_signal and stop_signal.received():
            stopped.set()
        done = False
        for _ in range(200):
            try:
                kind, value = updates.get_nowait()
            except queue.Empty:
                break
            if kind == "feedback":
                popup.update(value)
            elif kind == "error":
                exit_code = 1
                print("Error: " + value, file=sys.stderr)
                messagebox.showerror("Bobo listener stopped", value, parent=root)
            elif kind == "done":
                done = True
        if done:
            if args.wav and popup.window is not None and not stopped.is_set():
                root.after(100, finish_preview)
            else:
                popup.hide()
                root.destroy()
        else:
            root.after(50, poll)

    def finish_preview():
        if popup.window is None or stopped.is_set():
            popup.hide()
            root.destroy()
        else:
            root.after(100, finish_preview)

    threading.Thread(target=run, daemon=True).start()
    root.after(50, poll)
    try:
        root.mainloop()
    finally:
        stopped.set()
        if stop_signal:
            stop_signal.close()
        if claim:
            claim[0].CloseHandle(claim[1])
    return exit_code


if __name__ == "__main__":
    sys.exit(main() or 0)
