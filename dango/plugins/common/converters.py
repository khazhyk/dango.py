"""Converters..."""
import asyncio
import re
import typing

import discord
from discord.ext.commands import Converter, ParamDefault, converter, errors

from . import paginator
from . import utils

tag_regex = re.compile(r'(.*)#(\d{4})')
lax_id_regex = re.compile(r'([0-9]{15,21})$')
mention_regex = re.compile(r'<@!?([0-9]+)>$')


async def disambiguate(ctx, matches):
    if len(matches) == 1:
        return matches[0]

    matches = sorted(matches, key=lambda x: x.discriminator)

    pager = paginator.GroupLinesPaginator(ctx, [
        "%d: %s" % (idx + 1, match) for
        (idx, match) in enumerate(matches)
        ], title="Multiple matches, select one...", maxlines=10)

    pager_task = utils.create_task(pager.send())

    try:
        msg = await ctx.bot.wait_for('message', timeout=10,
                check=lambda m: m.author.id == ctx.author.id and
                                m.channel.id == ctx.channel.id)
    except asyncio.TimeoutError:
        raise errors.BadArgument("Timed out waiting for disambiguation...")
    else:
        try:
            idx = int(msg.content) - 1
        except ValueError:
            raise errors.BadArgument("{} is not a number... try again?".format(msg.content))

        if idx < 0 or idx >= len(matches):
            raise errors.BadArgument("Bad index... Try typing what you see in the embed...?")

        return matches[idx]
    finally:
        await pager.close()
        pager_task.cancel()
        if pager.msg:
            utils.create_task(pager.msg.delete())


class UserMemberConverter(Converter):
    """Resolve users/members.

    If given a username only checks current server. (Ease of use)

    If given a full DiscordTag or ID, will check current server for Member,
    fallback to bot for User.
    """

    async def get_by_id(self, ctx, user_id):
        """Exact user_id lookup."""
        if ctx.guild:
            result = ctx.guild.get_member(user_id)
        if not result:
            result = ctx.bot.get_user(user_id)
        return result

    async def get_by_name(self, ctx, user_name):
        """Lookup by name.

        Returns list of possible matches. For user#discrim will only give exact
        matches.

        Try doing an exact match.
        If within guild context, fall back to inexact match.
        If found in current guild, return Member, else User.
        (Will not do bot-wide inexact match)
        """
        tag_match = tag_regex.match(user_name)

        if tag_match:
            def pred(member):
                return member.name == tag_match.group(1) and member.discriminator == tag_match.group(2)

            result = None
            if ctx.guild:
                result = discord.utils.get(ctx.guild.members, name=tag_match.group(1), discriminator=tag_match.group(2))
            if not result:
                result = discord.utils.get(ctx.bot.users, name=tag_match.group(1), discriminator=tag_match.group(2))
            if result:
                return [result]

        if ctx.guild:
            user_name = user_name.lower()
            def pred(member):
                return (member.nick and member.nick.lower() == user_name) or member.name.lower() == user_name
            return [m for m in ctx.guild.members if pred(m)]
        return []

    async def find_match(self, ctx, argument):
        """Get a match...

        If we have a mention, try and get an exact match.
        If we have a number, try lookup by id.
        Fallback to lookup by name.

        Disambiguate in case we have multiple name results.
        """
        mention_match = mention_regex.match(argument)
        if mention_match:
            return await self.get_by_id(ctx, int(mention_match.group(1)))

        lax_id_match = lax_id_regex.match(argument)
        if lax_id_match:
            result = await self.get_by_id(ctx, int(lax_id_match.group(1)))
            if result:
                return result

        results = await self.get_by_name(ctx, argument)
        if results:
            return await disambiguate(ctx, results)

    async def convert(self, ctx, argument):
        match = await self.find_match(ctx, argument)

        if not match:
            raise errors.BadArgument(
                'User "{}" not found'.format(argument))
        return match


ChannelConverter = typing.Union[
    converter.TextChannelConverter,
    converter.VoiceChannelConverter,
    converter.CategoryChannelConverter]


class AnyImage(Converter):
    """Match anything that can be converted to an image.

    - User
    - Url (TODO: consider only allowing proxied images - wait for embed)
    """

    async def convert(self, ctx, argument):
        if argument.startswith("http://") or argument.startswith("https://"):
            return argument
        member = await UserMemberConverter().convert(ctx, argument)

        return member.avatar_url_as(format="png")


MESSAGE_ID_RE = re.compile(r'^(?:(?P<channel_id>[0-9]{15,21})[-/:])?(?P<message_id>[0-9]{15,21})$')
MESSAGE_LINK_RE = re.compile(
    r'^https?://(?:(ptb|canary)\.)?discordapp\.com/channels/'
    r'(?:([0-9]{15,21})|(@me))'
    r'/(?P<channel_id>[0-9]{15,21})/(?P<message_id>[0-9]{15,21})$')


class MessageIdConverter(Converter):
    """Match message_id, channel-message_id, or jump url to a discord.Message

    Message must be in the current guild.
    """

    async def convert(self, ctx, argument):
        match = MESSAGE_ID_RE.match(argument) or MESSAGE_LINK_RE.match(argument)
        if not match:
            raise errors.BadArgument("{} doesn't look like a message to me...".format(argument))

        msg_id = int(match.group("message_id"))
        channel_id = int(match.group("channel_id") or ctx.channel.id)
        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            raise errors.BadArgument("Channel {} not found".format(channel_id))

        if not ctx.author.permissions_in(channel).read_messages:
            raise errors.CheckFailure("You don't have permission to view this channel")

        return (channel, msg_id)


class AuthorAvatar(ParamDefault):

    async def default(self, ctx):
        return ctx.author.avatar_url_as(format="png")


class LastImage(ParamDefault):
    """Default param which finds the last image in chat.

    Can be None."""

    async def default(self, ctx):
        async for message in utils.CachedHistoryIterator(ctx, limit=100):
            for embed in message.embeds:
                if embed.thumbnail and embed.thumbnail.proxy_url:
                    return embed.thumbnail.proxy_url
            for attachment in message.attachments:
                if attachment.proxy_url:
                    return attachment.proxy_url
