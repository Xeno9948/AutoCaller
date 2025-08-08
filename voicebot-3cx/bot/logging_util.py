# bot/logging_util.py
import logging
import logging.handlers
import os
import sys
import csv
import json
from datetime import datetime
from rich.logging import RichHandler

LOG_DIR = "logs"

# --- Custom Record Attribute Filter ---

class TurnDataFilter(logging.Filter):
    """This filter only allows log records with a 'turn_data' attribute."""
    def filter(self, record):
        return hasattr(record, 'turn_data')

class NoTurnDataFilter(logging.Filter):
    """This filter blocks log records with a 'turn_data' attribute."""
    def filter(self, record):
        return not hasattr(record, 'turn_data')

# --- Custom Handlers for Turn Data ---

class CsvTurnHandler(logging.FileHandler):
    """A logging handler that writes turn data to a CSV file."""
    def __init__(self, filename, **kwargs):
        log_dir = os.path.dirname(filename)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        super().__init__(filename, mode='a', encoding='utf-8', **kwargs)
        self.writer = csv.writer(self.stream)

        self.stream.seek(0, 2)
        if self.stream.tell() == 0:
            self.writer.writerow(["ts", "asr_text", "llm_text", "stt_ms", "llm_ms", "tts_ms", "turn_ms", "errors"])
            self.flush()

    def emit(self, record):
        if not hasattr(record, 'turn_data'):
            return

        data = record.turn_data
        self.writer.writerow([
            data.get("ts", datetime.utcnow().isoformat()),
            data.get("asr_text", "").replace('\n', '\\n'),
            data.get("llm_text", "").replace('\n', '\\n'),
            data.get("stt_ms", 0),
            data.get("llm_ms", 0),
            data.get("tts_ms", 0),
            data.get("turn_ms", 0),
            str(data.get("errors", "")).replace('\n', '\\n'),
        ])
        self.flush()

class JsonlTurnHandler(logging.FileHandler):
    """A logging handler that writes turn data to a JSONL file."""
    def __init__(self, filename, **kwargs):
        log_dir = os.path.dirname(filename)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        super().__init__(filename, mode='a', encoding='utf-8', **kwargs)

    def emit(self, record):
        if not hasattr(record, 'turn_data'):
            return

        data = record.turn_data
        if "ts" not in data:
            data["ts"] = datetime.utcnow().isoformat()

        # Ensure error is a string
        if "errors" in data and not isinstance(data["errors"], str):
            data["errors"] = str(data["errors"])

        self.stream.write(json.dumps(data) + '\n')
        self.flush()


# --- Main Setup Function ---

def setup_logging(debug: bool = False):
    """
    Configures the main application logger and the turn logger.
    Call this once at the start of the application.
    """
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = logging.DEBUG if debug else getattr(logging, log_level_str, logging.INFO)

    # --- Root Logger for general app logging ---
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Console Handler (Rich) - filters out turn_data records
    rich_handler = RichHandler(
        rich_tracebacks=True,
        log_time_format="[%X]",
        show_path=False,
        tracebacks_suppress=[__import__('rich')]
    )
    rich_handler.setFormatter(logging.Formatter("%(name)-16s: %(message)s"))
    rich_handler.addFilter(NoTurnDataFilter())
    root_logger.addHandler(rich_handler)

    # Rotating File Handler for general logs
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    log_file_path = os.path.join(LOG_DIR, "voicebot.log")
    file_handler = logging.handlers.RotatingFileHandler(
        log_file_path, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8'
    )
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # --- Turn Logger for structured turn data ---
    turn_logger = logging.getLogger("turn_logger")
    turn_logger.setLevel(logging.INFO)
    turn_logger.propagate = False # Do not pass to root logger

    if turn_logger.hasHandlers():
        turn_logger.handlers.clear()

    turn_logger.addFilter(TurnDataFilter())

    # CSV Handler
    csv_handler = CsvTurnHandler(os.path.join(LOG_DIR, "turns.csv"))
    turn_logger.addHandler(csv_handler)

    # JSONL Handler
    jsonl_handler = JsonlTurnHandler(os.path.join(LOG_DIR, "turns.jsonl"))
    turn_logger.addHandler(jsonl_handler)

    # --- Set noisy library log levels higher ---
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("sounddevice").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("webrtcvad").setLevel(logging.WARNING)

    logging.info(f"Logging setup complete. Level: {logging.getLevelName(log_level)}")
    if log_level == logging.DEBUG:
        logging.debug("Debug mode is ON.")

# How to use:
#
# 1. In your main script (e.g., run.py), call `setup_logging()` early.
#
# 2. In any module, get a logger:
#    import logging
#    log = logging.getLogger(__name__)
#    log.info("This is a standard log message.")
#    log.debug("This is a debug message.")
#
# 3. To log a conversation turn:
#    turn_logger = logging.getLogger("turn_logger")
#    turn_data = {
#        "asr_text": "Hello world",
#        "llm_text": "Hi there!",
#        "stt_ms": 120, "llm_ms": 450, "tts_ms": 200, "turn_ms": 770,
#        "errors": ""
#    }
#    # The first argument to info is a descriptive message for the general log file if needed
#    # The `extra` dict is what gets processed by the custom handlers.
#    turn_logger.info("Conversation turn processed", extra={'turn_data': turn_data})
