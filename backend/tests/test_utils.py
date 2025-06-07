import logging
import json
from io import StringIO
from pathlib import Path

# -----------------------------------------------------------------------------
# 📌 Utility Function 1: capture_logs_while_running
# -----------------------------------------------------------------------------
def capture_logs_while_running(func):
    """
    Run a function and capture any log messages generated during its execution.

    This is useful in test cases where you want to verify that specific logging
    output occurred — for example, to confirm that a warning, error, or info
    message was logged during processing.

    Args:
        func (Callable): A function to execute. It should take no arguments.

    Returns:
        tuple:
            - result: The actual return value of the function.
            - logs (str): A string containing all log output captured.
    """
    log_stream = StringIO()  # Temporary in-memory buffer for log output
    handler = logging.StreamHandler(log_stream)  # Direct logs to buffer
    logger = logging.getLogger()

    logger.addHandler(handler)  # Attach custom handler
    logger.setLevel(logging.INFO)  # Ensure INFO-level logs are captured

    try:
        result = func()  # Run the target function
    finally:
        logger.removeHandler(handler)  # Clean up so logs don’t duplicate later

    return result, log_stream.getvalue()  # Return function result and captured logs

# -----------------------------------------------------------------------------
# 📌 Utility Function 2: load_expected_data
# -----------------------------------------------------------------------------
def load_expected_data(test_file_path: Path):
    """
    Load expected data for a test from a JSON file.
    """
    logging.info(f"🧪 Utils: Loading test data from {test_file_path}")  # ✅ ADD THIS LINE

    with open(test_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    expected_count = data.get("expected", {}).get("numValidTracks", 0)
    expected_logs = data.get("expectedLogs", [])

    return expected_count, expected_logs
