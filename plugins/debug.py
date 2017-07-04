import asyncio
import logging

from dango import plugin
from discord.ext.commands import command

log = logging.getLogger(__name__)


def dump_tasks():
    tasks = asyncio.Task.all_tasks()

    for task in tasks:
        try:
            task.print_stack()
        except Exception as e:
            print(e)


@plugin()
class Debug:

    async def on_ready(self):
        log.info("Ready!")

    @command()
    async def test(self, ctx):
        await ctx.send("\N{AUBERGINE}" * 2001)
