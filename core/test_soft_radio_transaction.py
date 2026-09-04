import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "install" / "soft-radio-transaction.sh"


class SoftRadioTransactionTests(unittest.TestCase):
    def setUp(self):
        bash = shutil.which("bash")
        if not bash and os.name == "nt":
            candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"
            bash = str(candidate) if candidate.exists() else None
        if not bash:
            self.skipTest("bash is required")
        self.bash = bash
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "root"
        self.backups = Path(self.temporary.name) / "backups"
        self.original = {
            "/etc/asterisk/rpt.conf": "generic rpt fixture\n",
            "/etc/asterisk/simpleusb.conf": "generic radio fixture\n",
            "/etc/asterisk/websocket_client.conf": "generic websocket fixture\n",
            "/etc/bluenode/remote-admin.json": '{"enabled": true}\n',
        }
        for logical, content in self.original.items():
            target = self.path(logical)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        self.script = str(SCRIPT)
        root = str(self.root)
        backups = str(self.backups)
        if os.name == "nt":
            def unix_path(value):
                return subprocess.run(
                    [self.bash, "-lc", 'cygpath -u "$1"', "_", value],
                    capture_output=True, text=True, check=True).stdout.strip()
            self.script = unix_path(self.script)
            root = unix_path(root)
            backups = unix_path(backups)
        self.environment = dict(os.environ,
            BLUENODE_TRANSACTION_ROOT=root,
            BLUENODE_TRANSACTION_BACKUP_ROOT=backups)

    def tearDown(self):
        self.temporary.cleanup()

    def path(self, logical):
        return self.root / logical.lstrip("/")

    def run_script(self, *arguments, check=True):
        result = subprocess.run([self.bash, self.script, *arguments],
            env=self.environment, capture_output=True, text=True)
        if check and result.returncode:
            self.fail(f"transaction command failed: {result.stderr.strip()}")
        return result

    def snapshot(self):
        result = self.run_script("snapshot")
        return result.stdout.strip().split("transaction=", 1)[1]

    def host_path(self, value):
        if os.name != "nt":
            return Path(value)
        converted = subprocess.run(
            [self.bash, "-lc", 'cygpath -w "$1"', "_", value],
            capture_output=True, text=True, check=True).stdout.strip()
        return Path(converted)

    def test_rollback_restores_preexisting_files_and_only_removes_recorded_creations(self):
        transaction = self.snapshot()
        remote_admin = self.path("/etc/bluenode/remote-admin.json")
        websocket = self.path("/etc/asterisk/websocket_client.conf")
        remote_admin.write_text("changed\n", encoding="utf-8")
        websocket.write_text("changed\n", encoding="utf-8")
        created = self.path("/etc/bluenode/soft-radio.json")
        created.parent.mkdir(parents=True, exist_ok=True)
        created.write_text("fixture\n", encoding="utf-8")
        self.run_script("mark-created", transaction, "/etc/bluenode/soft-radio.json")
        unrecorded = self.path("/etc/bluenode/soft-radio-websocket-client.conf")
        unrecorded.write_text("not made by this transaction\n", encoding="utf-8")

        self.run_script("rollback", transaction)
        self.run_script("rollback", transaction)

        self.assertEqual(remote_admin.read_text(encoding="utf-8"),
                         self.original["/etc/bluenode/remote-admin.json"])
        self.assertEqual(websocket.read_text(encoding="utf-8"),
                         self.original["/etc/asterisk/websocket_client.conf"])
        self.assertFalse(created.exists())
        self.assertTrue(unrecorded.exists())

    def test_incomplete_inventory_refuses_rollback_without_mutation(self):
        transaction_value = self.snapshot()
        transaction = self.host_path(transaction_value)
        remote_admin = self.path("/etc/bluenode/remote-admin.json")
        websocket = self.path("/etc/asterisk/websocket_client.conf")
        remote_admin_before = remote_admin.read_bytes()
        websocket_before = websocket.read_bytes()
        inventory = transaction / "inventory"
        inventory.write_text(inventory.read_text(encoding="utf-8").splitlines()[0] + "\n",
                             encoding="utf-8")
        result = self.run_script("rollback", transaction_value, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(remote_admin.read_bytes(), remote_admin_before)
        self.assertEqual(websocket.read_bytes(), websocket_before)

    def test_remote_admin_cannot_be_marked_as_created(self):
        self.path("/etc/bluenode/remote-admin.json").unlink()
        transaction = self.snapshot()
        remote_admin = self.path("/etc/bluenode/remote-admin.json")
        remote_admin.write_text("new unrelated file\n", encoding="utf-8")
        result = self.run_script("mark-created", transaction,
                                 "/etc/bluenode/remote-admin.json", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.run_script("rollback", transaction)
        self.assertTrue(remote_admin.exists())


if __name__ == "__main__":
    unittest.main()
