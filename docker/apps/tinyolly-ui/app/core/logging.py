"""Logging configuration with OpenTelemetry instrumentation"""

import logging
import sys
import os

from opentelemetry.instrumentation.logging import LoggingInstrumentor

from ..config import settings


def setup_logging():
    """Configure logging with stdout handler and OpenTelemetry instrumentation"""
    # Initialize OpenTelemetry logging instrumentation
    # This will automatically inject trace_id and span_id into log records
    LoggingInstrumentor().instrument(set_logging_format=True)
    
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)  # Ensure logs go to stdout
        ]
    )


logger = logging.getLogger(__name__)
