import asyncio
import logging

from dango import checks
from dango import dcog
from dango import utils
from discord.ext.commands import command

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
    """Various debugging commands."""

    def __init__(self, config):
        pass

    async def on_ready(self):
        log.info("Ready!")

    async def on_command(self, ctx):
        log.debug("Command triggered: command=%s author=%s msg=%s",
                  ctx.command.qualified_name, ctx.author, ctx.message.content)

    @command()
    async def test(self, ctx):
        await ctx.send("\N{AUBERGINE}")

    @command()
    @checks.is_owner()
    async def sh(self, ctx, *, cmd):
        with ctx.typing():
            stdout, stderr = await utils.run_subprocess(cmd)

        if stderr:
            out = "stdout:\n{}\nstderr:\n{}".format(stdout, stderr)
        else:
            out = stdout

        await ctx.send("```{}```".format(out))
