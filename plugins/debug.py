import asyncio
import logging
import os

from dango import dcog
from discord.ext.commands import command
import psutil

log = logging.getLogger(__name__)


def dump_tasks():
    tasks = asyncio.Task.all_tasks()

    for task in tasks:
        try:
            task.print_stack()
        except Exception as e:
            print(e)


@dcog()
class Debug:

    async def on_ready(self):
        log.info("Ready!")

    @command()
    async def test(self, ctx):
        await ctx.send("\N{AUBERGINE}" * 1)

    @command()
    async def stats(self, ctx):
        await ctx.send(
            "Using {:.2f} MiB of memory (RSS)".format(
                psutil.Process(os.getpid()).memory_full_info().rss / (1024 * 1024)
            ))
