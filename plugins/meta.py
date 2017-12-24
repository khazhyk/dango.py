import os
from datetime import datetime
from datetime import timedelta
import inspect

from dango import checks
from dango import dcog
import discord
from discord.ext.commands import command
from discord.ext.commands import errors
from discord.ext.commands import group
import pip
import psutil

from .common import utils

try:
    pip_util = pip.util
except AttributeError:
    pip_util = pip.utils
discord_version = discord.utils.get(
    pip_util.get_installed_distributions(), project_name="discord.py").version


SOURCE_URL = "https://github.com/khazhyk/dango.py/tree/master"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


class NoSuchCommand(Exception):
    """Command does not exist."""

    def __init__(self, cmd_name):
        super().__init__(cmd_name)
        self.cmd_name = cmd_name


class NoSuchSubCommand(Exception):
    """SubCommand does not exist."""

    def __init__(self, cmd, sub):
        super().__init__(cmd, sub)
        self.cmd = cmd
        self.sub = sub


class NoSubCommands(Exception):
    """SubCommand does not exist. Additionally, no subcommands exist."""

    def __init__(self, cmd):
        super().__init__(cmd)
        self.cmd = cmd


def resolve_command(bot, *args):
    try:
        cmd = bot.all_commands[args[0]]  # Raises if no such command.
    except KeyError:
        raise NoSuchCommand(args[0])

    subcmd = cmd
    for arg in args[1:]:
        try:
            subcmd = subcmd.all_commands[arg]
        except KeyError:
            raise NoSuchSubCommand(subcmd, arg)
        except AttributeError:
            raise NoSubCommands(subcmd)

    return subcmd


def get_cog_or_cmd_callback(ctx, *cmd_name):
    if len(cmd_name) == 1:
        cog = ctx.bot.get_cog(cmd_name[0])
        if cog:
            return cog.__class__
    try:
        cmd = resolve_command(ctx.bot, *cmd_name)
    except NoSubCommands as e:
        raise errors.BadArgument("`{}` has no subcommands".format(
            e.cmd.qualified_name))
    except NoSuchSubCommand as e:
        raise errors.BadArgument("`{}` has no subcommand {}".format(
            e.cmd.qualified_name, e.sub))
    except NoSuchCommand as e:
        raise errors.BadArgument("No such command or cog `{}`".format(
            e.cmd_name))
    return cmd.callback


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
        embed.set_footer(text="dangopy | discord.py v{}".format(discord_version))
        # embed.add_field(name="Messages", value="%d messages\n%d commands" % (messages, commands))
        # embed.add_field(name="Shards", value=shard_id(ctx.bot))

        await ctx.send(embed=embed)

    @command()
    async def source(self, ctx, *cmd_name):
        """Link to the source of a command or cog.

        If no name is provided, links to the root of the project."""
        if not cmd_name:
            return await ctx.send(SOURCE_URL)

        cog_or = get_cog_or_cmd_callback(ctx, *cmd_name)

        # srcfile seems to always be in unix/forward slash path, regardless of os
        srcfile = inspect.getsourcefile(cog_or)
        srclines, srclineno = inspect.getsourcelines(cog_or)

        lines = "L{}-L{}".format(srclineno, srclineno + len(srclines) - 1)
        url = srcfile.replace(BASE_DIR, SOURCE_URL) + "#" + lines

        await ctx.send(url)

    @command()
    @checks.is_owner()
    async def reload(self, ctx, extension):
        """Reloads an extension."""
        try:
            ctx.bot.unload_extension(extension)
            ctx.bot.load_extension(extension)
        except BaseException:
            await ctx.send("\N{THUMBS DOWN SIGN}")
            raise
        else:
            await ctx.send("\N{THUMBS UP SIGN}")

    @command()
    async def largestservers(self, ctx):
        """Show the 5 largest servers the bot sees."""
        servers = sorted(ctx.bot.guilds, key=lambda x: -len(x.members))

        msg = ""
        for i in range(0, 10):
            msg += "{0}: {1} members.\n".format(
                servers[i].name, len(servers[i].members))

        await ctx.send(msg)

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
            bulk=can_mass_purge)
        await ctx.message.add_reaction('\u2705')
