import logging
import traceback
from dango import dcog
import discord
from discord.ext.commands import errors

from .common import utils

log = logging.getLogger(__name__)


def tbtpl(exp):
    return (type(exp), exp, exp.__traceback__)


IGNORED = (
    errors.CommandNotFound,
    errors.DisabledCommand,
    errors.NoPrivateMessage
)

ERROR_MAP = utils.TypeMap({
    errors.BadArgument: "Bad argument: {exp}",
    errors.MissingRequiredArgument:
        "Missing argument: {exp.param.name}. Run `` {ctx.prefix}help "
        "{ctx.command.qualified_name} `` for more info.",
    errors.CommandError: "Error running command: {exp}",
    errors.CheckFailure: "Permissions error: {exp}",
    discord.errors.Forbidden: "I don't have permission: {exp.text}",
})


@dcog()
class CommandErrors:
    """Central cog for generic error messages.

    This handles error messages for generic error types e.g. BadArgument
    """

    def __init__(self, config):
        self.verbose_errors = config.register("verbose_errors", False)
        pass

    async def on_command_error(self, ctx, exp):
        main_exp = exp

        if isinstance(exp, IGNORED):
            return

        if isinstance(exp, errors.CommandInvokeError):
            exp = exp.original

        msg = ERROR_MAP.lookup(type(exp))
        if msg:
            await ctx.send(msg.format(exp=exp, ctx=ctx))
            return

        if isinstance(exp, discord.errors.HTTPException) and exp.response.status == 500:
            msg = "Discord broke, try again."
        elif self.verbose_errors.value:
            msg = "```{}```".format("".join(traceback.format_exception(*tbtpl(main_exp))))
        else:
            msg = "An unknown error occured."

        await ctx.send(msg)
        log.error("Unhandled error dispatching '%s' in '%s'", ctx.command.qualified_name,
                  ctx.message.content, exc_info=tbtpl(main_exp))
