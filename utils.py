import io
import logging
import os
import sys
from typing import Optional

def setup_logging(debug_mode: bool = False, log_file: Optional[str] = None):
    """Set up logging configuration."""
    # Set root logger to INFO by default, DEBUG only if explicitly requested
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug_mode else logging.INFO)

    # Clear any existing handlers
    root_logger.handlers = []

    # Create formatter
    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    formatter = logging.Formatter(log_format)

    # Add console handler with UTF-8 encoding to avoid Windows cp1252 errors
    # on characters like ★ (U+2605) or → (U+2192)
    utf8_stream = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    console_handler = logging.StreamHandler(stream=utf8_stream)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    
    # Add file handler if log file specified
    if log_file:
        # Create directory if it doesn't exist
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG if debug_mode else logging.INFO)
        root_logger.addHandler(file_handler)
        logging.info(f"Logging to file: {log_file}")
    
    # Configure specific loggers with appropriate levels
    loggers = {
        'AssociativeSemanticMemory': logging.INFO,
        'VectorKnowledgeGraph': logging.INFO,
        'DocumentProcessor': logging.INFO,
        'DocumentProcessor.WebPageSource': logging.INFO,
        'requests': logging.WARNING,  # Reduce HTTP request logging
        'urllib3': logging.WARNING,   # Reduce HTTP connection logging
    }
    
    for logger_name, level in loggers.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        logger.propagate = True  # Ensure logs propagate to root logger
    
    # Set logging parameters
    logging.captureWarnings(True)  # Capture warnings as logs
    
    # Force immediate flush of logs
    for handler in root_logger.handlers:
        handler.flush()
        if isinstance(handler, logging.FileHandler):
            os.fsync(handler.stream.fileno()) 