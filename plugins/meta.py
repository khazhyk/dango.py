import os
from datetime import datetime
from datetime import timedelta

from dango import dcog
from dango import utils
import discord
from discord.ext.commands import command
from discord.ext.commands import errors
from discord.ext.commands import group
import psutil


@dcog()
class Meta:
    """Information about the bot itself."""

    def __init__(self, config):
        pass

    @command(aliases=['rev', 'stats', 'info'])
    async def about(self, ctx):
        """Info about bot."""
        cmd = r'git log -3 --pretty="[{}](https://github.com/khazhyk/dango.py/commit/%H) %s (%ar)"'
        if os.name == "posix":
            cmd = cmd.format(r'\`%h\`')
        else:
            cmd = cmd.format('`%h`')
        stdout, _ = await utils.run_subprocess(cmd)

        embed = discord.Embed(description='Latest Changes:\n' + stdout)
        embed.title = "spoo.py Server Invite"
        embed.url = "https://discord.gg/0j3CB6tlXwou6Xb1"
        embed.color = 0xb19bd9

        embed.set_author(
            name=ctx.bot.user.name, icon_url=ctx.bot.user.avatar_url)
        embed.set_thumbnail(url=ctx.bot.user.avatar_url)

        servers = len(ctx.bot.guilds)
        members = sum(len(g.members) for g in ctx.bot.guilds)
        members_online = sum(1 for g in ctx.bot.guilds
                             for m in g.members
                             if m.status != discord.Status.offline)
        text_channels = sum(len(g.text_channels) for g in ctx.bot.guilds)
        voice_channels = sum(len(g.voice_channels) for g in ctx.bot.guilds)
        memory = psutil.Process(os.getpid()).memory_full_info().rss / (1024 * 1024)
        # messages = 10
        # commands = 10

        embed.add_field(
            name="Members",
            value="%d total\n%d online" % (members, members_online))
        embed.add_field(
            name="Channels",
            value="%d text\n%d voice" % (text_channels, voice_channels))
        embed.add_field(name="Servers", value=servers)
        embed.add_field(name="Process", value="%.2fMiB RSS" % memory)
        embed.set_footer(text="dangopy | discord.py v{}".format(
            discord.__version__))
        # embed.add_field(name="Messages", value="%d messages\n%d commands" % (messages, commands))
        # embed.add_field(name="Shards", value=shard_id(ctx.bot))

        await ctx.send(embed=embed)

    @group(invoke_without_command=True)
    async def clean(self, ctx, max_messages: int=100):
        """Clean up the bot's messages.

        Uses batch delete if bot has manage_message permission, otherwise uses
        individual delete (limited to 5/sec). Note that if using batch delete,
        Discord does not allow deleting messages older than two (2) weeks.
        """
        if (max_messages > 100):
            raise errors.BadArgument("Won't clean more than 100 messages!")

        can_mass_purge = ctx.channel.permissions_for(ctx.guild.me).manage_messages

        await ctx.channel.purge(
            limit=max_messages, check=lambda m: m.author == ctx.bot.user,
            before=ctx.message, after=datetime.utcnow() - timedelta(days=14),
            no_bulk=not can_mass_purge)
        await ctx.message.add_reaction('\u2705')
