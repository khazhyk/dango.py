import logging
import traceback
from dango import dcog, Cog
import discord
from discord.ext.commands import errors

from .common import utils

log = logging.getLogger(__name__)


def tbtpl(exp):
    return (type(exp), exp, exp.__traceback__)


IGNORED = (
    errors.CommandNotFound,
    errors.DisabledCommand,
)

ERROR_MAP = utils.TypeMap({
    errors.ConversionError: None,  # Probably a programming error...
    errors.BadArgument: "Bad argument: {exp}",
    errors.MissingRequiredArgument:
        "Missing argument: {exp.param.name}. Run `` {ctx.prefix}help "
        "{ctx.command.qualified_name} `` for more info.",
    errors.NoPrivateMessage: "This command only works in guilds.",
    errors.CommandError: "Error running command: {exp}",
    errors.CheckFailure: "Permissions error: {exp}",
    discord.errors.Forbidden: "I don't have permission: {exp.text}",
})


@dcog()
class CommandErrors(Cog):
    """Central cog for generic error messages.

    This handles error messages for generic error types e.g. BadArgument
    """

    def __init__(self, config):
        self.verbose_errors = config.register("verbose_errors", False)
        pass

    @Cog.listener()
    async def on_command_error(self, ctx, exp):
        try:
            main_exp = exp

            if isinstance(exp, IGNORED):
                return

            if isinstance(exp, errors.CommandInvokeError):
                exp = exp.original

            if isinstance(exp, errors.CheckFailure):
                log.debug("Check failure debugging for '%s' in '%s'", ctx.command.qualified_name,
                          ctx.message.content, exc_info=tbtpl(main_exp))

            msg = ERROR_MAP.lookup(type(exp))
            if msg:
                await ctx.send(msg.format(exp=exp, ctx=ctx))
                return

            if isinstance(exp, discord.errors.HTTPException) and exp.response.status in range(500, 600):
                msg = "Discord broke, try again."
            elif self.verbose_errors.value:
                msg = "```{}```".format(utils.clean_triple_backtick(
                        "".join(traceback.format_exception(*tbtpl(main_exp)))))
            else:
                msg = "An unknown error occured."

            log.error("Unhandled error dispatching '%s' in '%s'", ctx.command.qualified_name,
                          ctx.message.content, exc_info=tbtpl(main_exp))
            await ctx.send(msg)
        except:
            log.exception("Unhandled error in on_command_error")
            await ctx.send("An unknown error occured while trying to report an error.")
