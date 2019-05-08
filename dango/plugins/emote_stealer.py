import collections
import random
import re
import typing

import discord
from dango import dcog, Cog
from discord import PartialEmoji
from discord.ext.commands import command
from discord.ext.commands import errors

from .common.paginator import ListPaginator
from .common.converters import AnyImage, LastImage, SearchEmojiConverter
from .common import checks
from .common import utils


def idc_emoji_or_just_string(val):
    match = re.match(r'<(?P<animated>a)?:(?P<name>[a-zA-Z0-9_]+):(?P<id>[0-9]+)>$', val)
    if match:
        return PartialEmoji(name=match.group("name"), id=match.group("id"), animated=bool(match.group("animated")))
    return PartialEmoji(name=val.replace(':', ''), id=None, animated=False)  # guess it's not animated

idc_emoji = typing.Union[PartialEmoji, str]


@dcog()
class Emoji(Cog):
    def __init__(self, config):
        pass

    @command(aliases=["guild_emotes"])
    async def guild_emojis(self, ctx):
        """List emojis on this server.

        Note: will only list emoji this bot can send. Some twitch integration emoji
        (that do not require colons) cannot be sent by bots.
        """
        emojis = [
            "{0} - \{0}".format(emoji) for emoji in ctx.guild.emojis if emoji.require_colons
        ]

        if emojis:
            await ListPaginator.from_lines(ctx, emojis, "Guild Emojis").send()
        else:
            await ctx.message.add_reaction(":discordok:293495010719170560")

    @command(aliases=["find_emotes"])
    async def find_emojis(self, ctx, *search_emojis: idc_emoji_or_just_string):
        """Find all emoji sharing the same name and the servers they are from.

        Note: will only list emoji this bot can send. Some twitch integration emoji
        (that do not require colons) cannot be sent by bots.
        """
        found_emojis = [
            emoji for emoji in ctx.bot.emojis for search_emoji in search_emojis
            if emoji.name.lower() == search_emoji.name.lower() and emoji.require_colons
        ]
        if found_emojis:
            by_guild = collections.defaultdict(list)
            for e in found_emojis:
                by_guild[e.guild].append(e)

            lines = ("{}: {}".format(g, "".join(map(str,emojis))) for g, emojis in by_guild.items())
            await ListPaginator.from_lines(ctx, lines, "Found Emojis").send()
        else:
            await ctx.message.add_reaction(":discordok:293495010719170560")

    @command(aliases=["search_emotes"])
    async def search_emojis(self, ctx, *query_strings: str):
        """Find all emoji containing query string.

        Note: will only list emoji this bot can send. Some twitch integration emoji
        (that do not require colons) cannot be sent by bots.
        """
        found_emojis = [
            emoji for emoji in ctx.bot.emojis for query_string in query_strings
            if query_string.lower() in emoji.name.lower() and emoji.require_colons
        ]
        if found_emojis:
            by_guild = collections.defaultdict(list)
            for e in found_emojis:
                by_guild[e.guild].append(e)

            lines = ("{}: {}".format(g, "".join(map(str,emojis))) for g, emojis in by_guild.items())
            await ListPaginator.from_lines(ctx, lines, "Found Emojis").send()

        else:
            await ctx.message.add_reaction(":discordok:293495010719170560")

    @command()
    async def nitro(self, ctx, *, rest):
        """Send a random emoji with this name.

        Note: will only use emoji this bot can send. Some twitch integration emoji
        (that do not require colons) cannot be sent by bots.
        """
        rest = rest.lower()
        found_emojis = [emoji for emoji in ctx.bot.emojis
                        if emoji.name.lower() == rest and emoji.require_colons]
        if found_emojis:
            await ctx.send(str(random.choice(found_emojis)))
        else:
            await ctx.message.add_reaction(":discordok:293495010719170560")

    @command(aliases=["random_emote"])
    async def random_emoji(self, ctx):
        """Show a random emoji this bot can use."""
        try:
            await ctx.send(str(random.choice(
                [emoji for emoji in ctx.bot.emojis if emoji.require_colons])))
        except ValueError:
            await ctx.message.add_reaction(":discordok:293495010719170560")

    @command(aliases=["bigmote"])
    async def bigmoji(self, ctx, emoji: idc_emoji):
        """Link to the full sized image for an emoji."""
        if isinstance(emoji, PartialEmoji):
            await ctx.send(str(emoji.url))
        else:
            await ctx.send(utils.emoji_url(emoji))


@dcog()
class EmoteStealer(Cog):
    """Steal emotes."""

    def __init__(self, config):
        self.emote_guild_ids = config.register("emote_guilds", [130086905223184384])

    async def upload_emoji(self, ctx, name, image):
        image = await utils.fetch_image(image)

        animated = discord.utils._get_mime_type_for_image(image) == "image/gif"

        for g in self.emote_guild_ids():
            g = ctx.bot.get_guild(g)
            if not g:
                continue

            count = sum(e.animated == animated for e in g.emojis)

            if count >= 50:
                continue

            emoji = await g.create_custom_emoji(
                name=name, image=image,
                reason="Uploaded by {} ({})".format(ctx.author, ctx.author.id))
            await ctx.message.add_reaction(emoji)
            return

        raise errors.CommandError("I can't upload that emoji anywhere :(")

    @checks.is_owner()
    @command(aliases=["make_emote"])
    async def make_emoji(self, ctx, name, image: AnyImage = LastImage):
        """Create an emoji!"""
        await self.upload_emoji(ctx, name, image)

    @checks.is_owner()
    @command(aliases=["show_emote"])
    async def show_emoji(self, ctx, emoji: SearchEmojiConverter):
        """Show info about an emoji!"""
        e = discord.Embed()
        e.title = emoji.name
        e.set_thumbnail(url=str(emoji.url))
        e.description = str(emoji)
        e.add_field(name="Guild", value=getattr(emoji, "guild", "Unknown"))
        e.add_field(name="Animated", value=emoji.animated)

        await ctx.send(embed=e)

    @checks.is_owner()
    @command(aliases=["steal_emote"])
    async def steal_emoji(self, ctx, emoji: SearchEmojiConverter, custom_name=None):
        """Steal an emoji!"""
        await self.upload_emoji(ctx, custom_name or emoji.name, emoji.url)
