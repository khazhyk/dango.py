
import logging

import discord.ext.commands
from discord.ext.commands import errors

from dango.core import dcog, Cog

log = logging.getLogger(__name__)


CONFIG_NAME = "grants"

EDITABLE_KEYS = {
    "guild_allow", "guild_deny", "permission_reset", "permission_allow", "permission_deny",
    "role_allow", "role_deny", "user_allow", "user_deny"
}
READ_ONLY_KEYS = {
    "default_guild_allow", "default_guild_deny", "default_permission_allow"
}

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

    def context(self, cog: discord.ext.commands.Cog):
        """Returns the grants handle for the cog.
        
        self.gh = grants_cog.context(self)

        self.gh.permission_allow(manage_members=["permissions"])

        then:
        self.gh.require("some.perm")
        """


    def cog_unload(self):
        # This is especially important since cog unload doesn't remove checks automatically
        self.bot.remove_check(self.check_grants, call_once=False)
        self.jsonconfig.unregister(CONFIG_NAME)

    async def check_grants(self, ctx):
        log.info(ctx.command)
        return True
    
    def validate_grants(self, full_config):
        # Idea for validation handler:
        # an "are you sure" context, similar to name disambig, for "warnings" but not invalid
        # e.g., adding a command node that doesn't exist
        for key, value in full_config.items():
            if key in READ_ONLY_KEYS:
                raise errors.BadArgument(f"{key} is read-only")
            if key not in EDITABLE_KEYS:
                raise errors.BadArgument(f"unknown key {key}")

    def on_grants_update(self, value):
        pass