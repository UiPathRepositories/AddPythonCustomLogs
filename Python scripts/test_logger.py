import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("Logger.py")
BATCH_PATH = Path(__file__).with_name("RunLogger.bat")
spec = importlib.util.spec_from_file_location("Logger", MODULE_PATH)
logger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logger)


class LoggerScriptTests(unittest.TestCase):
    def test_log_file_path_uses_the_project_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)

            self.assertEqual(
                logger.log_file_path(base_dir),
                base_dir / "runtime_log.txt",
            )

    def test_append_log_message_creates_file_with_json_log_record(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "runtime_log.txt"
            now = datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc)

            logger.append_log_message(
                log_path,
                "Script is running",
                loglevel="Warn",
                now=now,
            )

            record = json.loads(log_path.read_text(encoding="utf-8"))

            self.assertEqual(record["timestamp"], "2026-05-26T12:00:00+00:00")
            self.assertEqual(record["loglevel"], "Warn")
            self.assertEqual(record["message"], "Script is running")

    def test_batch_file_runs_logger_from_project_folder(self):
        content = BATCH_PATH.read_text(encoding="utf-8")

        self.assertIn('cd /d "%~dp0"', content)
        self.assertIn('python "%~dp0Logger.py"', content)


if __name__ == "__main__":
    unittest.main()
