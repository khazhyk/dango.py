import asyncio
import logging

from dango import dcog
import discord

from dango.plugins.common import utils

log = logging.getLogger(__name__)


@dcog(pass_bot=True)
class Status:

    def __init__(self, bot, config):
        self.bot = bot

        utils.create_task(self.update_presence())

    async def on_ready(self):
        await self.update_presence()

    async def update_presence(self):
        await self.bot.change_presence(
            status=discord.Status.invisible, afk=True)
