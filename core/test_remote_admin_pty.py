import os
import threading
import time
import unittest

import remote_admin


@unittest.skipUnless(os.name == "posix", "requires a POSIX pseudo-terminal")
class RemoteAdminPtyTests(unittest.TestCase):
    def test_noncanonical_hidden_input_preserves_printable_fixture(self):
        import pty
        master, slave = pty.openpty()
        tty_path = os.ttyname(slave)
        result = []
        failure = []

        def read_fixture():
            try:
                result.append(remote_admin.read_hidden_secret("Fixture: ", tty_path))
            except Exception as exc:  # pragma: no cover - assertion reports it
                failure.append(exc)

        thread = threading.Thread(target=read_fixture)
        thread.start()
        time.sleep(0.05)
        os.write(master, b"Synthetic-Long-Value!\n")
        thread.join(2)
        os.close(master)
        os.close(slave)
        self.assertFalse(thread.is_alive())
        self.assertFalse(failure)
        self.assertEqual(result, ["Synthetic-Long-Value!"])

    def test_backspace_is_handled_without_canonical_line_editing(self):
        import pty
        master, slave = pty.openpty()
        tty_path = os.ttyname(slave)
        result = []
        thread = threading.Thread(target=lambda: result.append(
            remote_admin.read_hidden_secret("Fixture: ", tty_path)))
        thread.start()
        time.sleep(0.05)
        os.write(master, b"Synthetic-X\x7fValue-Long!\n")
        thread.join(2)
        os.close(master)
        os.close(slave)
        self.assertEqual(result, ["Synthetic-Value-Long!"])


if __name__ == "__main__": unittest.main()
