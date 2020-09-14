
import logging

from discord.ext.commands import group, errors

from dango.core import dcog, Cog

log = logging.getLogger(__name__)


CONFIG_NAME = "grants"


@dcog(depends=["JsonConfig"], pass_bot=True)
class Grants(Cog):
    def __init__(self, bot, config, jsonconfig):
        del config

        self.bot = bot
        self.jsonconfig = jsonconfig
        jsonconfig.register(CONFIG_NAME, self.validate_grants, self.on_grants_update)
        # Note, call_once=True effectivly means can_run() doesn't use this check.
        # For the help command, this means it won't filter based on this check.
        bot.add_check(self.check_grants, call_once=False)

    def cog_unload(self):
        # This is especially important since cog unload doesn't remove checks automatically
        self.bot.remove_check(self.check_grants, call_once=False)
        self.jsonconfig.unregister(CONFIG_NAME)

    async def check_grants(self, ctx):
        log.info(ctx.command)
        return True
    
    def validate_grants(self, value):
        # Idea for validation handler:
        # an "are you sure" context, similar to name disambig, for "warnings" but not invalid
        # e.g., adding a command node that doesn't exist
        pass

    def on_grants_update(self, value):
        pass