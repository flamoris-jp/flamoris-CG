"""Regression for the actual restrictive-umask installation failure."""
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1]/"tools/activate_event_gateway.py"
spec = importlib.util.spec_from_file_location("cg_event_activation", MODULE_PATH)
activation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(activation)


@unittest.skipIf(os.name == "nt", "POSIX directory traversal permissions")
class ActivationPermissionsTests(unittest.TestCase):
    def test_restrictive_umask_root_and_nested_code_are_traversable(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/"code"
            previous = os.umask(0o077)
            try:
                target.mkdir(mode=0o755)
                module = target/"src/package/entry.py"
                module.parent.mkdir(mode=0o755, parents=True)
                module.write_text("# code, never a private configuration\n")
            finally:
                os.umask(previous)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o700)
            activation.seal_source_tree(target)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o755)
            self.assertEqual(stat.S_IMODE((target/"src").stat().st_mode), 0o755)
            self.assertEqual(stat.S_IMODE(module.parent.stat().st_mode), 0o755)
            self.assertEqual(stat.S_IMODE(module.stat().st_mode), 0o444)
            self.assertEqual(module.read_text(), "# code, never a private configuration\n")

    def test_sealing_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/"code"; target.mkdir()
            private = Path(directory)/"private"; private.write_text("private")
            private.chmod(0o600)
            (target/"link").symlink_to(private)
            with self.assertRaises(ValueError): activation.seal_source_tree(target)
            self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o600)

    def test_snapshot_rejects_changed_bytes_without_mutation(self):
        # Keep this test portable across non-root POSIX CI users. Ownership is
        # independently enforced by verify_snapshot; mock only that stat field.
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory); path = target/"code.py"; path.write_text("original")
            hashes = {"code.py": hashlib.sha256(path.read_bytes()).hexdigest()}
            path.write_text("changed")
            original_stat = Path.stat
            def root_stat(value, *args, **kwargs):
                info = original_stat(value, *args, **kwargs)
                fields = list(info); fields[4] = 0
                return os.stat_result(fields)
            with patch.object(Path, "stat", root_stat):
                with self.assertRaisesRegex(ValueError, "installed code changed"):
                    activation.verify_snapshot(target, hashes)
            self.assertEqual(path.read_text(), "changed")


if __name__ == "__main__":
    unittest.main()
