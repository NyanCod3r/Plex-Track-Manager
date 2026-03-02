"""
common_utils.py - Shared utilities for Plex-Track-Manager

Provides shared helpers for folder creation and generic retry logic.
"""

import os
import logging
import time


def createFolder(folder_path):
    try:
        os.makedirs(folder_path, exist_ok=True)
        logging.debug(f"Ensured folder exists: {folder_path}")
    except Exception as e:
        logging.error(f"Failed to create folder {folder_path}: {e}")


def retry_with_backoff(func, *args, max_retries=5, **kwargs):
    backoff = 1
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            logging.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {backoff}s...")
            time.sleep(backoff)
            backoff *= 2
    raise Exception("Max retries exceeded")