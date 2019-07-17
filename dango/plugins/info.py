"""Userinfo et. al."""
import codecs
import re
from datetime import datetime
from datetime import timedelta

from dango import dcog, Cog
import discord
from discord.ext import commands
from discord.ext.commands import command
from discord.ext.commands import errors
import humanize
import tabulate
import logging

from .common import converters
from .common import utils
from .common.utils import InfoBuilder
from .common.paginator import GroupLinesPaginator

log = logging.getLogger(__name__)

async def _send_find_results(ctx, matches):
    if len(matches) == 0:
        await ctx.send("No matches!")
    else:
        match_lines = ["`{}` {}#{}".format(
                member.id, utils.clean_formatting(member.name), member.discriminator)
            for member in matches]
        await GroupLinesPaginator(ctx, match_lines, "{} results".format(len(matches)), 30).send()


def _is_hard_to_mention(name):
    """Determine if a name is hard to mention."""
    codecs.register_error('newreplace', lambda x: (
        b" " * (x.end - x.start), x.end))

    encoderes, chars = codecs.getwriter('ascii').encode(name, 'newreplace')

    return re.search(br'[^ ][^ ]+', encoderes) is None


@dcog()
class Find(Cog):
    """Listing members."""

    def __init__(self, config):
        pass

    @command()
    @commands.guild_only()
    async def find(self, ctx, *, username):
        """Find users with simple matching."""
        username = username.lower()

        if len(username) < 2:
            raise errors.BadArgument("Username must be at least 2 characters.")

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
            if filter in member.name.lower():
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
    async def rolemembers(self, ctx, *, role: discord.Role):
        """List the members of a role."""
        if role == ctx.message.guild.default_role:
            raise errors.CommandError("Cannot list members for default role.")
        matches = [
            member for member in ctx.message.guild.members if role in member.roles]

        await _send_find_results(ctx, matches)

    @command()
    @commands.guild_only()
    async def findold(self, ctx, *, days: int):
        """Shows members that haven't logged in/been seen by the bot in the last `days` days."""
        now = datetime.utcnow()

        msg = ""
        tracking = ctx.bot.get_cog("Tracking")

        if not tracking:
            return

        cutoff = now - timedelta(days=days)

        if cutoff < ctx.message.guild.me.joined_at:
            msg += ("WARNING: The bot has only been in this server since {}, "
                    "you specified a cutoff of {}\n").format(
                ctx.message.guild.me.joined_at, cutoff)
            msg += ("This means that I don't have enough data to reliably say "
                    "who has been online in that time span.\n")

        old_members = []
        last_seens = await tracking.bulk_last_seen(ctx.message.guild.members)
        for (last_seen, last_spoke, server_last_spoke), member in zip(last_seens, ctx.message.guild.members):
            if last_seen < cutoff:
                old_members.append(
                    (str(member), member.id, last_spoke, last_seen, server_last_spoke))

        msg += tabulate.tabulate(
            old_members, tablefmt="simple",
            headers=("Member", "ID", "Last Spoke", "Last Seen", "Server Last Spoke"))

        await ctx.send(msg)

# Discord epoch
UNKNOWN_CUTOFF = datetime.utcfromtimestamp(1420070400.000)


def format_time(time):
    if time is None or time < UNKNOWN_CUTOFF:
        return "Unknown"
    return "{} ({} UTC)".format(
        humanize.naturaltime(time + (datetime.now() - datetime.utcnow())), time)

def format_timedelta(td):
    ts = td.total_seconds()
    return "{:02d}:{:06.3f}".format(
        int(ts//60),
        ts % 60)

def activity_string(activity):
    if isinstance(activity, (discord.Game, discord.Streaming)):
        return str(activity)
    elif isinstance(activity, discord.Activity):
        ret = activity.name
        if activity.details:
            ret += " ({})".format(activity.details)
        if activity.state:
            ret += " - {}".format(activity.state)
        return ret
    elif isinstance(activity, discord.Spotify):
        elapsed = datetime.utcnow() - activity.start
        return "{}: {} by {} from {} [{}/{}]".format(
            activity.name,
            activity.title or "Unknown Song",
            activity.artist or "Unknown Artist",
            activity.album or "Unknown Album",
            format_timedelta(elapsed),
            format_timedelta(activity.duration)
            )
    else:
        log.warning("Unhandled activity type: {} {}".format(
            type(activity), activity))
        return str(activity)


@dcog()
class Info(Cog):
    """Info about things."""

    def __init__(self, config):
        pass

    @command()
    @commands.guild_only()
    async def channelinfo(self, ctx, *, channel: converters.ChannelConverter=None):
        """Get info about a channel."""
        channel = channel or ctx.message.channel
        i = InfoBuilder()
        i.add_field("Channel", "{0.name} ({0.id})".format(channel))
        i.add_field("Server", "{0.guild.name} ({0.guild.id})".format(channel))
        i.add_field("Type", "{}".format(type(channel).__name__))
        i.add_field("Created", format_time(channel.created_at))
        await ctx.send(i.code_block())

    @command()
    @commands.guild_only()
    async def topic(self, ctx, *, channel: converters.ChannelConverter=None):
        """Quote the channel topic at people."""
        if channel is None:
            channel = ctx.message.channel
        await ctx.send(("Channel topic: " + channel.topic) if channel.topic else "No topic set.")

    @command(aliases=["guildinfo"])
    @commands.guild_only()
    async def serverinfo(self, ctx):
        """Show information about a server."""
        server = ctx.message.guild
        text_count = len(server.text_channels)
        voice_count = len(server.voice_channels)
        text_hid = sum(
            1 for c in server.channels
            if c.overwrites_for(server.default_role).read_messages is False)

        roles = ", ".join([r.name for r in sorted(server.roles, key=lambda r: -r.position)])

        i = InfoBuilder()

        i.add_field("Server", server.name)
        i.add_field("ID", server.id)
        i.add_field("Region", server.region)
        i.add_field("Members", "{} ({} online)".format(
            len(server.members),
            sum(1 for m in server.members if m.status is not discord.Status.offline)))
        i.add_field(
            "Chats", "{} Text ({}) Hidden / {} Voice".format(text_count, text_hid, voice_count))
        i.add_field("Owner", server.owner)
        i.add_field("Created", format_time(server.created_at))
        i.add_field("Icon", server.icon_url)
        i.add_field("Roles", roles)

        await ctx.send(i.code_block())

    @command()
    async def userinfo(self, ctx, *, user: converters.UserMemberConverter=None):  # TODO - custom converter
        """Show information about a user."""
        if user is None:
            user = ctx.message.author

        tracking = ctx.bot.get_cog("Tracking")

        i = InfoBuilder()
        i.add_field("User", str(user))
        if isinstance(user, discord.Member) and user.nick:
            i.add_field("Nickname", user.nick)
        i.add_field("ID", user.id)
        if tracking is not None:
            names = ", ".join((await tracking.names_for(user))[:3])
            i.add_field("Names", names)
            if isinstance(user, discord.Member):
                nicknames = ", ".join((await tracking.nicks_for(user))[:3])
                if nicknames:
                    i.add_field("Nicks", nicknames)
        i.add_field("Shared Guilds", sum(g.get_member(user.id) is not None for g in ctx.bot.guilds))
        i.add_field("Created", format_time(user.created_at))
        if isinstance(user, discord.Member):
            i.add_field("Joined", format_time(user.joined_at))
        if tracking is not None:
            last_seen = await tracking.last_seen(user)
            i.add_field("Last Seen", format_time(last_seen.last_seen))
            i.add_field("Last Spoke", format_time(last_seen.last_spoke))
            if isinstance(user, discord.Member):
                i.add_field("Spoke Here", format_time(last_seen.server_last_spoke))
        if isinstance(user, discord.Member):
            i.add_field("Roles", ", ".join(
                [r.name for r in sorted(user.roles, key=lambda r: -r.position)]))
        if isinstance(user, discord.Member) and user.activities:
            i.add_field("Playing", "\n".join(activity_string(a) for a in user.activities))

        await ctx.send(i.code_block())

    @command()
    async def roleinfo(self, ctx, *, role: discord.Role):
        """Displays information about a role."""
        rd = InfoBuilder([
            ('Name', role.name),
            ('ID', role.id),
            ('Members', sum(1 for member in role.guild.members if role in member.roles)),
            ('Created', role.created_at),
            ('Managed', role.managed),
            ('Position', role.position),
            ('Permissions', role.permissions.value),
            ('Color', "#{:06x}".format(role.color.value)),
            ('Hoist', role.hoist),
            ('Mentionable', role.mentionable)
        ])

        await ctx.send(rd.code_block())

    @command()
    async def avatar(self, ctx, *, user: converters.UserMemberConverter=None):
        """Show a user's avatar."""
        if user is None:
            user = ctx.message.author

        await ctx.send(str(user.avatar_url_as(static_format='png')))

    @command()
    async def defaultavatar(self, ctx, *, user: converters.UserMemberConverter=None):
        """Show the default avatar for a user.

        (If a user has a custom avatar, it will show what it would be if they removed it).
        """
        if user is None:
            user = ctx.message.author

        await ctx.send(str(user.default_avatar_url))
