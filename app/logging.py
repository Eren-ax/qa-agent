import os
import traceback

from pythonjsonlogger.json import JsonFormatter

from app.config import app_config


class DatadogJsonFormatter(JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["env"] = os.environ.get("DD_ENV", app_config.stage)
        if record.exc_info and record.exc_info[1] is not None:
            exc_type, exc_value, exc_tb = record.exc_info
            log_record["error.kind"] = exc_type.__name__
            log_record["error.message"] = str(exc_value)
            log_record["error.stack"] = "".join(
                traceback.format_exception(exc_type, exc_value, exc_tb)
            )
            log_record.pop("exc_info", None)
