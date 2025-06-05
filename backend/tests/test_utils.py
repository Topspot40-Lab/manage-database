import logging
import json
from io import StringIO
from pathlib import Path


def capture_logs_while_running(func):
    """
    Captures all logs emitted during the execution of `func`.

    Returns:
        result: The return value of `func`.
        logs: A string containing the captured logs.
    """
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    try:
        result = func()
    finally:
        logger.removeHandler(handler)

    return result, log_stream.getvalue()


def load_expected_data(test_file_path: Path):
    """
    Loads expected results and expected log lines from the JSON test file.

    Returns:
        expected_count (int): Number of expected valid tracks.
        expected_logs (List[str]): List of expected log messages.
    """
    with open(test_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    expected_count = data.get("expected", {}).get("numValidTracks", 0)
    expected_logs = data.get("expectedLogs", [])
    return expected_count, expected_logs
