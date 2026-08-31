#!/usr/bin/env python3
"""Run a single-process Redis worker; queue messages contain analysis IDs only."""

import logging

from app.services.analysis_jobs import QUEUE_NAME, get_redis, process_analysis


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("fincontract.worker")
    redis_client = get_redis()
    logger.info("worker started; listening on %s", QUEUE_NAME)
    try:
        while True:
            message = redis_client.blpop(QUEUE_NAME, timeout=5)
            if message:
                _, analysis_id = message
                logger.info("processing analysis_id=%s", analysis_id)
                process_analysis(analysis_id, redis_client)
                logger.info("finished analysis_id=%s", analysis_id)
    except KeyboardInterrupt:
        logger.info("worker stopped")
