import logging

def get_step_logger(step_id: str) -> logging.Logger:
    """
    Return a named logger (e.g., 'STEP_1.B') that integrates with the logging config.
    """
    return logging.getLogger(step_id)
