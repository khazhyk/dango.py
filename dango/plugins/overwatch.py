import logging
import re

import aiohttp
from dango import dcog
import discord
from discord.ext.commands import command, group, errors, Converter, UserConverter
from pachimari import BattleTag, OverwatchProfile, Platform, PCRegion, CONRegion

log = logging.getLogger(__name__)

def battle_tag(value):
    try:
        return BattleTag.from_tag(value)
    except ValueError:
        raise errors.BadArgument("Invalid battletag")


class user_or_name(Converter):

    def convert(self):
        value = self.argument
        match = re.match(r'<@!?([0-9]+)>', value)
        if match is None:
            return battle_tag(value)
        else:
            return UserConverter(self.ctx, self.argument).convert()


def get_regions(platform):
    if platform is Platform.pc:
        return PCRegion
    else:
        return CONRegion


async def find_tag(client, tag):
    for platform in Platform:
        tag.platform = platform
        for region in get_regions(platform):
            tag.region = region
            async with client.head(tag.profile_url, allow_redirects=True) as resp:
                if resp.status == 404:
                    continue
                elif resp.status != 200:
                    log.error("Unknown error looking up battletag %s", resp)
                    raise errors.CommandError(
                        "There was an unknown error looking up your battletag")
                else:
                    return tag
    raise errors.BadArgument("Could not find that user in any region!")


@dcog(depends=["AttributeStore"])
class Overwatch():

    def __init__(self, config, attr):
        self.attr = attr
        # Double register this command.
        # bot.commands['owc'] = self.competitive

    @command(aliases=["setoverwatch", "setow", "setbt"])
    async def setbattletag(self, ctx, tag: battle_tag):
        """Sets the Blizzard BattleTag associated with this Discord account.

        Tags are of the format <platform>/<region>/username#number, or username#number. For example: "pc/us/noob#0001".
        If platform and region are not specified, I will search. If the incorrect one is chosen, please specify the platform and region.
        """
        async with aiohttp.ClientSession() as client:
            if tag.is_complete:
                async with client.head(tag.profile_url) as resp:
                    if resp.status == 404:
                        raise errors.BadArgument(
                            "That battletag does not match a user")
                    elif resp.status != 200:
                        raise errors.CommandError(
                            "There was an unknown error setting your battletag")
                    else:
                        await self.attr.set_attributes(ctx.message.author, blizzard_battletag=tag.tag)
                        await ctx.send("Updated your battletag to {}".format(tag))
            else:
                tag = await find_tag(client, tag)
                await self.attr.set_attributes(ctx.message.author, blizzard_battletag=tag.tag)
                await ctx.send("Updated your battletag to {}".format(tag))

    async def _get_overwatch_profile(self, ctx, tag):
        if isinstance(tag, discord.abc.User):
            tag = await self.attr.get_attribute(tag, "blizzard_battletag")
            if not tag:
                raise errors.BadArgument(
                    "User has no associated battletag, have them use `setow` or `setbt`")
            else:
                tag = BattleTag.from_tag(tag)

        with ctx.typing():
            async with aiohttp.ClientSession() as client:
                if not tag.is_complete:
                    tag = await find_tag(client, tag)

                async with client.get(tag.profile_url) as resp:
                    return OverwatchProfile.from_html(tag, await resp.text())

    @group(aliases=["ow", "owc"], invoke_without_command=True)
    async def overwatch(self, ctx, tag: user_or_name=None):
        """Get Overwatch stats for a given user.

        May supply a Discord mention, or a BattleTag.
        Tags are of the format <platform>/<region>/username#number, or username#number. For example: "pc/us/noob#0001".
        If platform and region are not specified, I will search. If the incorrect one is chosen, please specify the platform and region.
        """
        if ctx.invoked_with == "owc":
            return await self.competitive.invoke(ctx)

        if not tag:
            tag = ctx.message.author

        prof = await self._get_overwatch_profile(ctx, tag)

        if not prof.quick_play:
            raise errors.BadArgument(
                "Player has no quick play stats available.")

        content = """
{0.tag.tag_private} Level {0.level} - {0.quick_play.all_heroes.game.games_won} Wins
{1.game.time_played} played. {1.combat.eliminations} eliminations, {1.combat.deaths} deaths.
Average: {1.average.damage_done} damage, {1.average.eliminations} elims, {1.average.final_blows} final blows, {1.average.deaths} deaths, {1.average.healing_done} healing
""".format(prof, prof.quick_play.all_heroes)

        await ctx.send("```prolog{}```".format(content))

    @overwatch.command(aliases=['c'], pass_context=True)
    async def competitive(self, ctx, tag: user_or_name=None):
        if not tag:
            tag = ctx.message.author
        prof = await self._get_overwatch_profile(ctx, tag)

        if not prof.competitive_play:
            raise errors.BadArgument(
                "Player has no competitive stats available.")

        if prof.competitive_play.all_heroes.game.games_won and \
                prof.competitive_play.all_heroes.game.games_played:
            win_percent = 100 * (prof.competitive_play.all_heroes.game.games_won /
                                 prof.competitive_play.all_heroes.game.games_played)
        else:
            win_percent = 0
        content = """
{0.tag.tag_private} Level {0.level} Rank {0.rank} - {1.game.games_won} Wins / {1.game.games_played} Games ({2:.02f}%)
{1.game.time_played} played. {1.combat.eliminations} eliminations, {1.combat.deaths} deaths.
Average: {1.average.damage_done} damage, {1.average.eliminations} elims, {1.average.final_blows} final blows, {1.average.deaths} deaths, {1.average.healing_done} healing
""".format(prof, prof.competitive_play.all_heroes, win_percent)

        await ctx.send("```prolog{}```".format(content))
