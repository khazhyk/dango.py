import asyncio
import collections
import datetime
import logging
import time
import re

import aiohttp
from dango import dcog, Cog
import discord
from discord.ext.commands import command
from discord.ext.commands import converter
from discord.ext.commands import default
from discord.ext.commands import errors
from discord.utils import cached_property
import humanize
from lru import LRU
import osuapi
from osuapi.model import OsuMode

from .common import converters
from .common import utils

log = logging.getLogger(__name__)

# date ranked, UTC+0 for now
DATE_OFFSET = (datetime.datetime.now() - datetime.datetime.utcnow())


class StringOrMentionConverter(converter.Converter):
    async def convert(self, ctx, argument):
        if argument.startswith("+"):
            return argument[1:]
        try:
            return await converters.UserMemberConverter().convert(ctx, argument)
        except errors.BadArgument:
            return argument


def osu_map_url(value):
    match = re.match(
        r'https://osu.ppy.sh/(?:s/(?P<beatmapset>[0-9]+)|b/(?P<beatmap>0-9]+))/?.*', value)
    if match.group("beatmapset"):
        return dict(beatmapset=match.group("beatmapset"))
    elif match.group("beatmap"):
        return dict(beatmap=match.group("beatmap"))
    raise errors.BadArgument("Not recognized as a beatmap url!")


def get_mode(command_name: str):
    if command_name.startswith("osu"):
        return OsuMode.osu
    if command_name.startswith("taiko"):
        return OsuMode.taiko
    if command_name.startswith("mania"):
        return OsuMode.mania
    if command_name.startswith("ctb"):
        return OsuMode.ctb


class OsuRichPresence:

    def __init__(self, activity: discord.Activity):
        if activity.name != "osu!":
            raise InvalidArgumentError("not osu!")
        self._activity = activity

    @cached_property
    def username(self):
        if not self._activity.large_image_text:
            return None
        return self._activity.large_image_text.split('(')[0].strip()

    @cached_property
    def rank(self):
        return int(re.match(r".* \(rank #(.*)\)", self._activity.large_image_text).group(1).replace(",", ""))

    @property
    def state(self):
        return self._activity.state

    @property
    def multiplayer_lobby(self):
        if not self._activity.party.get('size'):
            return None
        return self._activity.state


@dcog(depends=["AttributeStore"])
class Osu(Cog):
    """osu! API commands."""

    def __init__(self, config, attr):
        self.attr = attr
        self.api_key = config.register("api_key")
        self.osuapi = osuapi.OsuApi(
            self.api_key(), connector=osuapi.AHConnector(
                aiohttp.ClientSession(loop=asyncio.get_event_loop())))
        self._osu_presence_username_cache = LRU(4<<10)

        self._beatmap_cache = LRU(256)

    def cog_unload(self):
        self.osuapi.close()

    async def _set_osu_username(self, user, username):
        """Set :user's osu account to :username. Returns api result."""
        osu_acct = await self._lookup_acct(username)

        await self.attr.set_attributes(user, osu_id=osu_acct.user_id)

        return osu_acct

    async def _lookup_acct(self, username, mode=OsuMode.osu):
        res = await self.osuapi.get_user(username, mode=mode)

        if len(res) == 0:
            raise errors.BadArgument(
                "There is no osu user by the name {}".format(username))

        return res[0]

    @Cog.listener()
    async def on_member_update(self, before, member):
        if member.activity and member.activity.name == "osu!" and isinstance(member.activity, discord.Activity):
            rp = OsuRichPresence(member.activity)
            if rp.username:
                self._osu_presence_username_cache[member.id] = rp.username

    @command()
    async def setosu(self, ctx, *, username: str):
        """Set your osu account to be remembered by the bot."""
        with ctx.typing():
            osu_acct = await self._set_osu_username(ctx.message.author, username)

        await ctx.send(
            "OK, set your osu account to {0.username} ({0.user_id})".format(
                osu_acct))

    @command(aliases=['osuwatch'])
    async def watchosu(self, ctx, *, account: StringOrMentionConverter=None):
        """Shows a osu spectate link

        Use + to give a raw account name. e.g.:
        osu +cookiezi
        osu @ppy
        """
        account = account or ctx.message.author

        if isinstance(account, discord.abc.User):
            user_osu_id = await self.attr.get_attribute(account, 'osu_id')

            if user_osu_id is None:
                await ctx.send(
                    "I don't know your osu name! "
                    "Use {}setosu <name> to set it!".format(ctx.prefix))
                return
        else:
            user_osu_id = account

        await ctx.send("<osu://spectate/{}>".format(user_osu_id))

    async def _get_osu_account(self, ctx, user, mode):
        osu_user_id = await self.attr.get_attribute(user, 'osu_id')

        if osu_user_id:
            return await self._lookup_acct(osu_user_id, mode=mode)

        if ctx.author.id != user.id:
            raise errors.BadArgument(
                "I don't know {}'s osu username!".format(user))

        presence_username = self._osu_presence_username_cache.get(user.id)

        clean_prefix = utils.clean_double_backtick(ctx.prefix)

        if presence_username:
            await ctx.send(
                "I don't know your osu username! I'm setting your osu username "
                "to {}, which rich presence showed you recently playing as. "
                "If this is wrong use ``{}setosu <username>``".format(
                presence_username, clean_prefix))
            return await self._set_osu_username(user, presence_username)

        await ctx.send(
            "I don't know your osu username! I'm setting your osu username "
            "to {}, if this is wrong use ``{}setosu <username>``".format(
                user.name, clean_prefix))
        return await self._set_osu_username(user, user.name)

    async def _get_beatmap(self, beatmap_id):
        if beatmap_id in self._beatmap_cache:
            return self._beatmap_cache[beatmap_id]
        beatmaps = await self.osuapi.get_beatmaps(beatmap_id=beatmap_id)
        if not beatmaps:
            return None
        self._beatmap_cache[beatmap_id] = beatmaps[0]
        return beatmaps[0]

    @command(aliases=['taikotop', 'ctbtop', 'maniatop'])
    async def osutop(self, ctx, *, account: StringOrMentionConverter=default.Author):
        """Show a user's top osu plays."""
        mode = get_mode(ctx.invoked_with)

        with ctx.typing():
            if isinstance(account, discord.abc.User):
                osu_acct = await self._get_osu_account(ctx, account, mode)
            else:
                osu_acct = await self._lookup_acct(account, mode=mode)

            top_scores = await self.osuapi.get_user_best(
                osu_acct.user_id, mode=mode)

        embed = discord.Embed()
        embed.title = osu_acct.username
        embed.url = "https://osu.ppy.sh/u/%s" % osu_acct.user_id
        embed.color = hash(str(osu_acct.user_id)) % (1 << 24)
        if isinstance(account, discord.abc.User):
            embed.set_author(
                name=str(account), icon_url=account.avatar_url_as(static_format="png"))

        if not top_scores:
            embed.description = "%s has not played %s" % (
                osu_acct.username, mode.name)
        else:
            map_descriptions = []

            expected_len = 0

            for score in top_scores:
                beatmap = await self._get_beatmap(score.beatmap_id)
                if not beatmap:
                    continue

                entry = (
                    "**{pp}pp - {rank}{mods} - {score.score:,} ({percent:.2f}%) {score.maxcombo}x - {map.difficultyrating:.2f} Stars** - {ago}\n"
                    "[{map.artist} - {map.title}[{map.version}]]({map.url}) by [{map.creator}](https://osu.ppy.sh/u/{map.creator_id})").format(
                        pp=score.pp,
                        rank=score.rank.upper(),
                        mods=" +{:s}".format(score.enabled_mods) if score.enabled_mods.value else "",
                        percent=100*score.accuracy(mode),
                        ago=humanize.naturaltime(score.date + DATE_OFFSET),
                        score=score,
                        map=beatmap)

                if expected_len + len(entry) + 1 <= 2048:
                    map_descriptions.append(entry)
                    expected_len += len(entry) + 1
                else:
                    break

            embed.description = "\n".join(map_descriptions)

        await ctx.send(embed=embed)

    @command(aliases=['taikorecent', 'ctbrecent', 'maniarecent'])
    async def osurecent(self, ctx, *, account: StringOrMentionConverter=None):
        """Show a user's recent osu plays.

        Use + to give a raw account name. e.g.:
        osu +cookiezi
        osu @ppy
        """
        account = account or ctx.message.author

        mode = {
            'osurecent': OsuMode.osu,
            'taikorecent': OsuMode.taiko,
            'maniarecent': OsuMode.mania,
            'ctbrecent': OsuMode.ctb
        }[ctx.invoked_with]

        with ctx.typing():
            if account is None:
                raise errors.BadArgument("Invalid mention...!")

            if isinstance(account, discord.abc.User):
                osu_acct = await self._get_osu_account(ctx, account, mode)
            else:
                osu_acct = await self._lookup_acct(account, mode=mode)

            recent_scores = await self.osuapi.get_user_recent(
                osu_acct.user_id, mode=mode)

        embed = discord.Embed()
        embed.title = osu_acct.username
        embed.url = "https://osu.ppy.sh/u/%s" % osu_acct.user_id
        embed.color = hash(str(osu_acct.user_id)) % (1 << 24)
        if isinstance(account, discord.abc.User):
            embed.set_author(
                name=str(account), icon_url=account.avatar_url_as(static_format="png"))

        if not recent_scores:
            embed.description = "%s hasn't played %s recently" % (
                osu_acct.username, mode.name)
        else:
            map_descriptions = []

            expected_len = 0

            for score in recent_scores:
                beatmap = await self._get_beatmap(score.beatmap_id)
                if not beatmap:
                    continue

                entry = (
                    "**{rank}{mods} - {score.score:,} ({percent:.2f}%) {score.maxcombo}x - {map.difficultyrating:.2f} Stars** - {ago}\n"
                    "[{map.artist} - {map.title}[{map.version}]]({map.url}) by [{map.creator}](https://osu.ppy.sh/u/{map.creator_id})").format(
                        rank=score.rank.upper(),
                        mods=" +{:s}".format(score.enabled_mods) if score.enabled_mods.value else "",
                        percent=100*score.accuracy(mode),
                        ago=humanize.naturaltime(score.date + DATE_OFFSET),
                        score=score,
                        map=beatmap)

                if expected_len + len(entry) + 1 <= 2048:
                    map_descriptions.append(entry)
                    expected_len += len(entry) + 1
                else:
                    break

            embed.description = "\n".join(map_descriptions)

        await ctx.send(embed=embed)

    @command(pass_context=True, aliases=['taiko', 'ctb', 'mania'])
    async def osu(self, ctx, *, account: StringOrMentionConverter=None):
        """Show a user's osu profile.

        Use + to give a raw account name. e.g.:
        osu +cookiezi
        osu @ppy
        """
        account = account or ctx.message.author

        mode = {
            'osu': OsuMode.osu,
            'taiko': OsuMode.taiko,
            'mania': OsuMode.mania,
            'ctb': OsuMode.ctb
        }[ctx.invoked_with]

        with ctx.typing():
            if account is None:
                raise errors.BadArgument("Invalid mention...!")

            if isinstance(account, discord.abc.User):
                osu_acct = await self._get_osu_account(ctx, account, mode)
            else:
                osu_acct = await self._lookup_acct(account, mode=mode)

            usrscore = await self.osuapi.get_user_best(
                osu_acct.user_id, limit=100, mode=mode)

        embed = discord.Embed()
        embed.title = osu_acct.username
        embed.url = "https://osu.ppy.sh/u/%s" % osu_acct.user_id
        embed.color = hash(str(osu_acct.user_id)) % (1 << 24)
        if isinstance(account, discord.abc.User):
            embed.set_author(
                name=str(account), icon_url=account.avatar_url_as(static_format="png"))
        embed.set_thumbnail(
            url="http://a.ppy.sh/%s?_=%s" % (osu_acct.user_id, time.time()))

        if not usrscore:
            embed.description = "%s has never played %s" % (
                osu_acct.username, ctx.invoked_with)
        else:
            embed.description = "#{0.pp_rank:,} ({0.pp_raw} pp)".format(osu_acct)
            fave_mod = collections.Counter(
                play.enabled_mods for play in usrscore).most_common()[0][0]
            bplay = usrscore[0]
            embed.add_field(
                name="Plays", value="{:,}".format(osu_acct.playcount))
            embed.add_field(
                name="Hits", value="{:,}".format(osu_acct.total_hits))
            embed.add_field(
                name="Acc", value="{:.2f}".format(osu_acct.accuracy))
            embed.add_field(
                name="Best Play", value="{:,}pp {:s}".format(bplay.pp, bplay.enabled_mods))
            embed.add_field(
                name="Favorite Mod", value="{:l}".format(fave_mod))

        await ctx.send(embed=embed)
