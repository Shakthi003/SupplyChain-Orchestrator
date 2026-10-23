"""
core/logging_config.py -- structured (JSON-lines) logging.

One line per event, e.g.
  {"ts":"2026-10-23T10:15:02+0000","level":"INFO","logger":"api","msg":"request",
   "request_id":"a1b2c3d4","method":"POST","path":"/events/EVT-002/analyze","status":200,"duration_ms":8412}

Why JSON: it can be grepped, filtered by request_id, or loaded by any log tool.

Env vars:
  LOG_LEVEL   DEBUG | INFO (default) | WARNING | ERROR
  LOG_FILE    optional path; logs go to stderr AND this file

Never log secrets (API keys) or full prompts/documents -- only ids, counts, timings.
"""

import contextvars
import json
import logging
import os
import sys

# Set by the API middleware; every log line written during that request carries it.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

# Fields passed via logger.info("msg", extra={...}) that we copy into the JSON line.
_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                data[key] = value
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str)


def setup_logging() -> None:
    """Configure the 'sco' logger tree once. Safe to call many times."""
    root = logging.getLogger("sco")
    if root.handlers:
        return
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    root.propagate = False

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    log_file = os.getenv("LOG_FILE")
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    for h in handlers:
        h.setFormatter(JsonFormatter())
        root.addHandler(h)


def get_logger(name: str) -> logging.Logger:
    """Use get_logger('api'), get_logger('agent'), get_logger('tools') ..."""
    setup_logging()
    return logging.getLogger(f"sco.{name}")
