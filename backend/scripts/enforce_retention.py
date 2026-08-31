#!/usr/bin/env python3

import argparse
import time

from app.config import get_settings
from app.services.retention import delete_expired_documents

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    while True:
        print(f"expired documents deleted: {delete_expired_documents()}", flush=True)
        if not args.loop:
            break
        time.sleep(get_settings().retention_interval_seconds)
