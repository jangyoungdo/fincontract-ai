#!/usr/bin/env python3
"""Run a single-process Redis worker; queue messages contain analysis IDs only."""

from app.services.analysis_jobs import QUEUE_NAME, get_redis, process_analysis


if __name__ == "__main__":
    redis_client = get_redis()
    while True:
        message = redis_client.blpop(QUEUE_NAME, timeout=5)
        if message:
            _, analysis_id = message
            process_analysis(analysis_id, redis_client)
