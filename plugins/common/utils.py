import asyncio
import logging

log = logging.getLogger(__name__)

def log_task(fut):
    if fut.exception():
        log.warn(fut.exception())

def create_task(thing):
    task = asyncio.ensure_future(thing)
    task.add_done_callback(log_task)
    return task
