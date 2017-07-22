"""Userinfo et. al."""
import codecs
import re
from datetime import datetime
from datetime import timedelta

from dango import dcog
from dango import utils
from discord.ext import commands
from discord.ext.commands import command
from discord.ext.commands import errors
import tabulate

async def _send_find_results(ctx, matches):
    if len(matches) == 0:
        await ctx.send("No matches!")
    else:
        await ctx.send("{} results.\n{}".format(
            len(matches), "\n".join(["`{}` {}#{}".format(
                member.id, utils.clean_formatting(
                    member.name),
                member.discriminator) for member in matches])))


def _is_hard_to_mention(name):
    """Determine if a name is hard to mention."""
    codecs.register_error('newreplace', lambda x: (
        b" " * (x.end - x.start), x.end))

    encoderes, chars = codecs.getwriter('ascii').encode(name, 'newreplace')

    return re.search(br'[^ ][^ ]+', encoderes) is None


@dcog()
class Find:
    """Listing members."""

    def __init__(self, config):
        pass

    @command()
    @commands.guild_only()
    async def find(self, ctx, *, username=""):
        """Find users with simple matching."""
        username = username.lower()

        if len(username) < 2:
            raise errors.BadArgument("")

        matches = [
            member for member
            in ctx.message.guild.members if username in member.name.lower()
        ]

        await _send_find_results(ctx, matches)

    @command()
    @commands.guild_only()
    async def finddups(self, ctx, *, filter=""):
        """Show members with identical names.

        Can specify a filter to only match members with a certain string in
        thier name.
        """
        buckets = {}

        for member in ctx.message.guild.members:
            if (filter in member.name.lower()):
                entry = buckets.get(member.name.lower(), [])
                entry.append(member)
                buckets[member.name.lower()] = entry

        matches = []

        for lowname, memlist in buckets.items():
            if len(memlist) > 1:
                matches.extend(memlist)

        await _send_find_results(ctx, matches)

    @command(aliases=['hardmention'])
    @commands.guild_only()
    async def findhardmention(self, ctx):
        """List members with difficult to mention usernames."""
        matches = [
            member for member
            in ctx.message.guild.members if _is_hard_to_mention(member.name)
        ]

        await _send_find_results(ctx, matches)

    @command()
    @commands.guild_only()
    @commands.cooldown(1, 86400, commands.BucketType.guild)
    async def findold(self, ctx, *, days: int):
        """Shows members that haven't logged in/been seen by the bot in the last `days` days.

        Stupidly inefficient command, ask spoopy to run it for you lol"""
        now = datetime.utcnow()

        msg = ""
        tracking = ctx.bot.get_cog("Tracking")

        if not tracking:
            return

        cutoff = now - timedelta(days=days)

        if (cutoff < ctx.message.guild.me.joined_at):
            msg += ("WARNING: The bot has only been in this server since {}, "
                    "you specified a cutoff of {}\n").format(
                ctx.message.guild.me.joined_at, cutoff)
            msg += ("This means that I don't have enough data to reliably say "
                    "who has been online in that time span.\n")

        old_members = []
        for member in ctx.message.guild.members:
            last_seen, last_spoke, server_last_spoke = await tracking.last_seen(member)

            if last_seen < cutoff:
                old_members.append(
                    (str(member), member.id, last_spoke, last_seen))

        msg += tabulate.tabulate(
            old_members, tablefmt="simple",
            headers=("Member", "ID", "Last Spoke", "Last Seen"))

        await ctx.send(msg)

