from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from controller import FloatingControl


class ControllerMenuTests(unittest.TestCase):
    def setUp(self):
        self.control = FloatingControl.__new__(FloatingControl)
        self.control.config = Path("config.json")
        self.control.running = False
        self.control.starting = False
        self.control.child = None
        self.control.rendered_status = None
        self.control.menu = Mock()
        self.control.menu.winfo_ismapped.return_value = False
        self.control.canvas = Mock()
        self.control.dot = "status-dot"

    @patch("controller.listener_running", return_value=False)
    def test_unchanged_polling_does_not_repaint_the_menu_or_icon(self, running):
        for _ in range(40):
            self.control.refresh_status()
        self.assertEqual(self.control.menu.entryconfigure.call_count, 3)
        self.control.canvas.itemconfigure.assert_called_once()

    @patch("controller.listener_running", return_value=True)
    def test_status_changes_are_deferred_while_menu_is_open(self, running):
        self.control.menu.winfo_ismapped.return_value = True
        for _ in range(40):
            self.control.refresh_status()
        self.assertTrue(self.control.running)
        self.control.menu.entryconfigure.assert_not_called()
        self.control.canvas.itemconfigure.assert_not_called()
        self.control.menu.winfo_ismapped.return_value = False
        self.control.refresh_status()
        self.control.menu.entryconfigure.assert_any_call(0, label="Listener running")
        self.control.canvas.itemconfigure.assert_called_once_with("status-dot", fill="#63dfaa")

    def test_an_open_menu_cannot_be_posted_repeatedly(self):
        self.control.menu.winfo_ismapped.return_value = True
        self.control.show_menu(SimpleNamespace(x_root=10, y_root=20))
        self.control.menu.tk_popup.assert_not_called()
