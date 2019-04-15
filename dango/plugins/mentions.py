from dango import dcog, Cog
from enum import Enum
import datetime
import discord
import logging
from discord.ext.commands import command, errors

from .common import utils

log = logging.getLogger(__name__)

class PmMentionMode(Enum):
    on = "on"
    off = "off"
    always = "always"
    mostly = "mostly"

    def __str__(self):
        return self.value

def resolve_pmmentionmode(value):
    try:
        return PmMentionMode(value)
    except ValueError:
        raise errors.BadArgument("PmMentionMode must be one of: {}".format(
            ", ".join(PmMentionMode.__members__.keys())))

def _format_message(message):
    if message.attachments:
        if message.attachments[0].url:
            attachments = message.attachments[0].url
        else:
            log.warning("Message found without url in attachments! {}".format(
                message.attachments))
            attachments = ""
    else:
        attachments = ""
    return "[{message.created_at:%Y-%m-%d %H:%M} UTC] {message.author}: {content} {attachments}\n".format(
        message=message,
        content=utils.clean_newline(message.content),
        attachments=attachments)

def fit_into(parts: list, limit: int=2000):
    """
    Joins the parts into larger parts of at most len limit
    """

    groups = []

    cur = ""

    for i in range(len(parts)):
        part = parts[i]
        if len(cur) + len(part) > limit:
            groups.append(cur)
            cur = ""
        cur += part

    if cur != "":
        groups.append(cur)

    return groups

@dcog(depends=["AttributeStore"], pass_bot=True)
class Mentions(Cog):
    """Mentions directly to your inbox!."""

    def __init__(self, bot, config, attr):
        self.proxy_token = config.register("proxy_token", "")  # TODO
        self.attr = attr
        self.bot = bot

    async def _get_mode(self, user: discord.User):
        return PmMentionMode(await self.attr.get_attribute(user, "pm_mentions_mode", "off"))

    async def _get_context(self, message: discord.Message):
        """Grab the last 4 messages before a message and format it properly."""
        context = [message]

        async for msg in utils.CachedHistoryIterator(self.bot, message.channel, limit=4, before=message):
            context.append(msg)

        context_msg = [
            _format_message(x)
            for x in context]
        context_msg.append("You were mentioned by {} ({}) on {} {}\nJump: {}\n".format(
            message.author.mention, utils.clean_formatting(message.author.name), message.channel.guild.name, message.channel.mention,
            utils.jump_url(message)))
        context_msg = list(reversed(context_msg))

        return context, context_msg


    async def _message_user(self, mention, message, context):
        # Can't pm ourselves.
        if mention.id == self.bot.user.id:
            return

        mode = await self._get_mode(mention)

        if mode is PmMentionMode.off:
            return

        if mode is PmMentionMode.on and mention.status is discord.Status.online:
            # if PmMentionMode.on, only send when idle or offline.
            return

        if not message.channel.permissions_for(mention).read_messages:
            return

        if context[0] is None:
            context[0], context[1] = await self._get_context(message)

        if mode is not PmMentionMode.always:
            for msg in context[0]:
                if (msg.author.id == mention.id) and ((message.created_at - msg.created_at) < datetime.timedelta(seconds=5)):
                    # Don't send a pm if they were recently speaking - this is to
                    # stop bot commands triggering this.
                    return

        try:
            for msg in fit_into(context[1]):
                await mention.send(msg)
        except discord.Forbidden as e:
            if "Cannot send messages to this user" in e.text:
                log.warn("User %s (%s) has blocked us, but had pmmentions set to %s. Disabling.",
                         str(mention), mention.id, mode)
                await self.attr.set_attributes(mention, pm_mentions_mode=PmMentionMode.off.value)

    @Cog.listener()
    async def on_message(self, message):
        if isinstance(message.channel, discord.DMChannel) or not message.mentions or message.author.id == self.bot.user.id:
            return

        if len(message.mentions) > 10:
            log.warning("Dropped message with more than 10 mentions!: {}".format(
                message.content))
            return

        context = [None, None]
        for mention in message.mentions:
            await self._message_user(mention, message, context)

    @command()
    async def pmmentions(self, ctx, mode: resolve_pmmentionmode=None):
        """Show or set your pmmentions mode.

        Valid modes are:
          - always: always send PMs when you are mentioned
          - mostly: won't send PMs if you spoke recently
          - on: send PMs when you are offline or idle
          - off: do not send PMs when you are mentioned
        """
        if mode:
            await self.attr.set_attributes(ctx.message.author, pm_mentions_mode=mode.value)
            await ctx.send("Set your pmmentions mode to: {}".format(mode))
        else:
            await ctx.send("Your pmmentions mode is currently: {}".format(await self._get_mode(ctx.message.author)))
