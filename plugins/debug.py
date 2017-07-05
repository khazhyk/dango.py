import asyncio
import logging
import os

from dango import checks
from dango import dcog
from dango import utils
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
    """Information about the bot."""

    async def on_ready(self):
        log.info("Ready!")

    @command()
    async def test(self, ctx):
        await ctx.send("\N{AUBERGINE}" * 1)

    @command()
    @checks.is_owner()
    async def sh(self, ctx, *, cmd):
        stdout, stderr = await utils.run_subprocess(cmd)

        if stderr:
            out = "stdout:\n{}\nstderr:\n{}".format(stdout, stderr)
        else:
            out = stdout

        await ctx.send("```{}```".format(out))
