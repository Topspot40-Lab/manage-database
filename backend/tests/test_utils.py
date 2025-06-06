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

    The test file must contain:
      - "expected": {
          "numValidTracks": <int>  # How many valid tracks we expect
        }
      - "expectedLogs": [
          "...expected log message 1...",
          "...expected log message 2..."
        ]

    This allows tests to validate not just the output but also the logs.

    Args:
        test_file_path (Path): Path to a test JSON file.

    Returns:
        tuple:
            - expected_count (int): Number of valid tracks expected from XAI.
            - expected_logs (List[str]): List of expected log strings.
    """
    with open(test_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Safely extract expected values
    expected_count = data.get("expected", {}).get("numValidTracks", 0)
    expected_logs = data.get("expectedLogs", [])

    return expected_count, expected_logs
