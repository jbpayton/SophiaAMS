import logging
import os
from typing import Optional

def setup_logging(debug_mode: bool = False, log_file: Optional[str] = None):
    """Set up logging configuration."""
    log_level = logging.DEBUG if debug_mode else logging.INFO
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Clear any existing handlers
    root_logger.handlers = []
    
    # Create formatter
    formatter = logging.Formatter(log_format)
    
    # Add console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Add file handler if log file specified
    if log_file:
        file_handler = logging.FileHandler(log_file, mode='a')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        logging.info(f"Logging to file: {log_file}") 