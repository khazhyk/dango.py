import os

from dango import dcog
from dango import utils
import discord
from discord.ext.commands import command
import psutil


@dcog()
class Meta:
    """Information about the bot itself."""

    @command(aliases=['rev', 'stats', 'info'])
    async def about(self, ctx):
        """Info about bot."""
        cmd = r'git log -3 --pretty="[{}](https://github.com/khazhyk/dango.py/commit/%H) %s (%ar)"'
        if os.name == "posix":
            cmd = cmd.format('\`%h\`')
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
        # embed.add_field(name="Messages", value="%d messages\n%d commands" % (messages, commands))
        # embed.add_field(name="Shards", value=shard_id(ctx.bot))

        await ctx.send(embed=embed)
