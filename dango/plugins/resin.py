from datetime import datetime, timedelta, timezone

from dango import dcog, Cog
import discord
from discord.ext.commands import command, group, errors
import humanize


class ScheduledTasks(Cog):
    """Schedule something to happen later."""


class Localization(Cog):
    """Allow users to store timezones and such, to format times and such."""


RESIN_CAP = 160
RESIN_INTERVAL = 8
INTERESTING_POINTS = [20, 40, 60, 80, 120, RESIN_CAP]


def tzs(dt):
    return dt.astimezone(tz=None).replace(tzinfo=None)


def resin_embed(current, last_resin=None, last_minutes_ago=None):
    if last_resin is None:
        last_resin = current
        last_minutes_ago = 0

    the_embed = discord.Embed()
    the_embed.description = f"**Current:** {current}/{RESIN_CAP}"

    for resin_point in INTERESTING_POINTS:
        if current >= resin_point:
            continue

        minutes_until = (RESIN_INTERVAL * (resin_point - last_resin)) - last_minutes_ago

        the_embed.add_field(name=f"{resin_point}/{RESIN_CAP}",
            value=f"{humanize.precisedelta(timedelta(minutes=minutes_until))} from now")
    return the_embed


@dcog(depends=["AttributeStore"])
class Resin(Cog):

    def __init__(self, config, attr):
        del config
        self.attr = attr

    @group(invoke_without_command=True)
    async def resin(self, ctx, current: int = None):
        """Estimate time until resin recharges.

        May be up to 8 minutes slow.
        """
        right_now = datetime.now(timezone.utc)
        if current is not None:
            # set current resin to current, re-calculate reminders
            await self.attr.set_attributes(
                ctx.author, resin_count=current, resin_date=right_now.timestamp())
            last_count = current
            last_date = right_now
            minutes_since_last_set = 0
        else:
            last_count = await self.attr.get_attribute(ctx.author, "resin_count")
            last_date_timestamp = await self.attr.get_attribute(ctx.author, "resin_date")

            if last_count is not None and last_date_timestamp:
                last_date = datetime.fromtimestamp(last_date_timestamp, timezone.utc)
                minutes_since_last_set = (right_now - last_date).total_seconds() // 60
                current = min(last_count + (minutes_since_last_set//RESIN_INTERVAL), RESIN_CAP)
            else:
                current = None

        if current is None:
            raise errors.BadArgument("I don't know, set ur resin at least once")

        the_embed = resin_embed(current, last_count, minutes_since_last_set)
        # Abuse timestamp localization
        the_embed.set_footer(text="Resin last set")
        the_embed.timestamp = last_date

        # Show current status
        await ctx.send(embed=the_embed)

    @resin.command(name="if")
    async def if_(self, ctx, current: int = None):
        the_embed = resin_embed(current)
        # Show current status
        await ctx.send(embed=the_embed)

    @resin.command()
    async def remind(self, ctx):
        await ctx.send("soontm")
