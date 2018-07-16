"""Converters..."""
import asyncio
import re

import discord
from discord.ext.commands import Converter, errors

from . import paginator
from . import utils

tag_regex = re.compile(r'(.*)#(\d{4})')
lax_id_regex = re.compile(r'([0-9]{15,21})$')
mention_regex = re.compile(r'<@!?([0-9]+)>$')


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
            def pred(member):
                return member.nick == user_name or member.name == user_name
            return [m for m in ctx.guild.members if pred(m)]
        return []

    async def disambiguate(self, ctx, matches):
        if len(matches) == 1:
            return matches[0]

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
            result = await self.get_by_id(ctx, lax_id_match.group(1))
            if result:
                return result

        results = await self.get_by_name(ctx, argument)
        if results:
            return await self.disambiguate(ctx, results)

    async def convert(self, ctx, argument):
        match = await self.find_match(ctx, argument)

        if not match:
            raise errors.BadArgument(
                'User "{}" not found'.format(argument))
        return match
