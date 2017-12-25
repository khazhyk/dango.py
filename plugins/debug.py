import asyncio
import copy
from contextlib import redirect_stdout
import logging
import io
import os
import sys

import aiohttp
from dango import checks
from dango import dcog
import discord
from discord.ext.commands import command
import objgraph

from .common import utils
from .common.paginator import EmbedPaginator

log = logging.getLogger(__name__)


@dcog(pass_bot=True)
class Debug:
    """Various debugging commands."""

    def __init__(self, bot, config):
        self.bot = bot

    async def on_ready(self):
        log.info("Logged in as")
        log.info(self.bot.user.name)
        log.info(self.bot.user.id)
        log.info('-------')

    async def on_command(self, ctx):
        log.debug("Command triggered: command=%s author=%s msg=%s",
                  ctx.command.qualified_name, ctx.author, ctx.message.content)

    @command(pass_context=True, no_pm=True)
    async def perminfo(self, ctx, chn: discord.TextChannel=None, usr: discord.User=None):
        """Show permissions for a user."""
        if usr is None:
            usr = ctx.message.author

        if chn is None:
            chn = ctx.message.channel

        perms = chn.permissions_for(usr)

        info = utils.InfoBuilder()

        for perm, value in perms:
            info.add_field(perm.replace("_", " ").title(), value)

        info.add_field("Value", "{:b}".format(perms.value))

        await ctx.send(info.code_block())

    @command()
    async def reactinfo(self, ctx):
        resp = ""
        async for msg in ctx.history(limit=10):
            for r in msg.reactions:
                if r.custom_emoji and r.emoji.guild:
                    resp += '%s ' % str(r.emoji.guild)
                resp += "{}: {} {}\n".format(r.emoji, r.count, r.me)

        await ctx.send(resp or "No info.")

    @command()
    @checks.is_owner()
    async def dump_tasks(self, ctx):
        lines = []
        for task in asyncio.Task.all_tasks():
            try:
                buf = io.StringIO()
                task.print_stack(file=buf)
                buf.seek(0)
                lines.append(buf.read())
            except Exception as e:
                lines.append(str(e))

        await EmbedPaginator.from_lines(ctx, lines).send()

    @command()
    async def test(self, ctx):
        await ctx.send("\N{AUBERGINE}")

    @command(name="objgraph")
    @checks.is_owner()
    async def objgraph_(self, ctx):
        mct = await ctx.bot.loop.run_in_executor(None, objgraph.most_common_types)
        await ctx.send(str(mct))

    @command()
    @checks.is_owner()
    async def objgrowth(self, ctx):
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            await ctx.bot.loop.run_in_executor(None, objgraph.show_growth)

        await ctx.send(stdout.getvalue())

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
    async def reload(self, ctx):
        """Reloads an extension.
        """
        try:
            ctx.bot.unload_extension(extension)
            ctx.bot.load_extension(extension)
        except BaseException:
            await ctx.send("\N{THUMBS DOWN SIGN}")
            raise
        else:
            await ctx.send("\N{THUMBS UP SIGN}")

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
    async def set_avatar(self, ctx, url=None):
        if not url:
            if ctx.message.attachments and ctx.message.attachments[0].url:
                url = ctx.message.attachments[0].url
        with aiohttp.ClientSession() as s:
            async with s.get(url) as resp:
                await ctx.bot.user.edit(avatar=await resp.read())
        await ctx.message.add_reaction(":helYea:236243426662678528")
