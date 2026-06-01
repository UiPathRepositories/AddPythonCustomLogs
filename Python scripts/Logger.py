import json
import time
from datetime import datetime
from pathlib import Path


LOG_FILE_NAME = "runtime_log.txt"
LOG_INTERVAL_SECONDS = 5
RUN_DURATION_SECONDS = 12 * 60 * 60
LOG_LEVEL = "Warn"
MESSAGE = "Script is running"


def project_folder() -> Path:
    return Path(__file__).resolve().parent


def log_file_path(base_dir=None):
    folder = Path(base_dir) if base_dir is not None else project_folder()
    return folder / LOG_FILE_NAME


def build_log_line(message, loglevel=LOG_LEVEL, now=None):
    timestamp = (now or datetime.now().astimezone()).isoformat(timespec="seconds")
    record = {
        "timestamp": timestamp,
        "loglevel": loglevel,
        "message": message,
    }
    return json.dumps(record, separators=(",", ":")) + "\n"


def append_log_message(
    log_path,
    message=MESSAGE,
    loglevel=LOG_LEVEL,
    now=None,
):
    target = Path(log_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("a", encoding="utf-8") as log_file:
        log_file.write(build_log_line(message, loglevel, now))


def run_logger(
    duration_seconds=RUN_DURATION_SECONDS,
    interval_seconds=LOG_INTERVAL_SECONDS,
    message=MESSAGE,
    loglevel=LOG_LEVEL,
    base_dir=None,
):
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be greater than 0")
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be greater than 0")

    target_log = log_file_path(base_dir)
    end_time = time.monotonic() + duration_seconds
    index = 0

    while time.monotonic() < end_time:
        append_log_message(target_log, message + f" ({index})", loglevel)
        remaining_seconds = end_time - time.monotonic()

        if remaining_seconds <= 0:
            break
        index += 1

        time.sleep(min(interval_seconds, remaining_seconds))


if __name__ == "__main__":
    run_logger()
