import asyncio
import logging
from datetime import datetime

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
    async def rtt(self, ctx):
        """Measures delay between message and reply.

        M2M: Discord generates message timestamp -> Discord generates reply timestamp
        RTT: Bot sends message -> Bot recieves own message
        """
        recv_time = ctx.message.created_at
        msg_content = "..."

        task = asyncio.ensure_future(ctx.bot.wait_for(
            "message", timeout=15,
            check=lambda m: (m.author == ctx.bot.user and
                             m.content == msg_content)))
        now = datetime.utcnow()
        sent_message = await ctx.send(msg_content)
        await task
        rtt_time = datetime.utcnow()

        await sent_message.edit(
            content="M2M: {:.2f}ms, RTT: {:.2f}ms".format(
                (sent_message.created_at - recv_time).total_seconds() * 1000,
                (rtt_time - now).total_seconds() * 1000
                )
            )

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
