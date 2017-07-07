import collections
import re
import aiohttp
from dango import dcog
import discord
from discord.ext.commands import command
from discord.ext.commands import converter
from discord.ext.commands import errors
import osuapi
from osuapi.model import OsuMode


class StringOrMentionConverter(converter.Converter):
    async def convert(self, ctx, argument):
        if argument.startswith("+"):
            return argument[1:]
        return await converter.MemberConverter().convert(ctx, argument)


def osu_map_url(value):
    match = re.match(
        r'https://osu.ppy.sh/(?:s/(?P<beatmapset>[0-9]+)|b/(?P<beatmap>0-9]+))/?.*', value)
    if match.group("beatmapset"):
        return dict(beatmapset=match.group("beatmapset"))
    elif match.group("beatmap"):
        return dict(beatmap=match.group("beatmap"))
    raise errors.BadArgument("Not recognized as a beatmap url!")


@dcog(depends=["AttributeStore"], pass_bot=True)
class Osu:
    """osu! API commands."""

    def __init__(self, bot, attr):
        self.attr = attr
        self.osuapi = osuapi.OsuApi(
            bot.config.osu_api_key, connector=osuapi.AHConnector(
                aiohttp.ClientSession(loop=bot.loop)))

    def __unload(self):
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

        await ctx.send(
            "I don't know your osu name! I'm setting your osu name to {}, "
            "if this is wrong use {}setosu <name>".format(
                user.name, ctx.prefix))
        return await self._set_osu_username(user, user.name)

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
                name=str(account), icon_url=account.avatar_url)
        embed.set_thumbnail(url="http://a.ppy.sh/%s" % osu_acct.user_id)

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
