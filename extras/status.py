import asyncio
import logging

from dango import dcog
import discord

log = logging.getLogger(__name__)

def log_task(fut):
    try:
        if fut.exception():
            e = fut.exception()
            log.warn("", exc_info=(type(e), e, e.__traceback__))
    except asyncio.CancelledError as e:
        log.debug("", exc_info=(type(e), e, e.__traceback__))


def create_task(thing):
    task = asyncio.ensure_future(thing)
    task.add_done_callback(log_task)
    return task


@dcog(pass_bot=True)
class Status:

    def __init__(self, bot, config):
        self.bot = bot

        create_task(self.update_presence())

    async def update_presence(self):
        await self.bot.wait_until_ready()
        await self.bot.change_presence(
            status=discord.Status.invisible, afk=True)
