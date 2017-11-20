import asyncio
import copy
import logging
import os
import sys

import aiohttp
from dango import checks
from dango import dcog
from dango import utils
import discord
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
    async def die(self, ctx):
        await ctx.message.add_reaction(":discordok:293495010719170560")
        await ctx.bot.logout()

    @command()
    @checks.is_owner()
    async def restart(self, ctx):
        await ctx.message.add_reaction(":helYea:236243426662678528")
        print(['python'] + sys.argv, sys.executable)
        os.execve(sys.executable, ['python', '-m', 'dango'], os.environ)

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

    @command(name="as")
    @checks.is_owner()
    async def as_(self, ctx, who: discord.Member, *, cmd):
        """Run a command impersonating another user."""
        fake_msg = copy.copy(ctx.message)

        # msg._update handles clearing cached properties
        fake_msg._update(ctx.message.channel, dict(
            content=ctx.prefix + cmd))
        fake_msg.author = who
        new_ctx = await ctx.bot.get_context(fake_msg)
        await ctx.bot.invoke(new_ctx)

    @command()
    @checks.is_owner()
    async def set_avatar(self, ctx, url):
        with aiohttp.ClientSession() as s:
            async with s.get(url) as resp:
                await ctx.bot.user.edit(avatar=await resp.read())
