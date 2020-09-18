
import logging

import discord
from discord.ext import commands
from discord.ext.commands import errors

from dango.core import dcog, Cog

log = logging.getLogger(__name__)


CONFIG_NAME = "grants"

EDITABLE_KEYS = {
    "guild_allow", "guild_deny", "permission_reset", "permission_allow",
    "role_allow", "role_deny", "user_allow", "user_deny"
}


def check(node_name=None):
    async def _(ctx):
        """Failsafe."""
        grants_cog = ctx.bot.get_cog("Grants")
        if not grants_cog:
            raise errors.CheckFailure("This command requires the Grants cog to be loaded")
        return True
    check_decorator = commands.check(_)

    # FIXME - should check for the footgun that a "explicit" node matches a implicit command name node
    def real_decorator(func):
        if isinstance(func, commands.Command):
            func = func.callback
        if node_name:
            try:
                func.__dango_grants__.add(node_name)
            except AttributeError:
                func.__dango_grants__ = {node_name}
        else:
            func.__dango_restricted__ = True
        return check_decorator(func)

    return real_decorator


class GrantsContext:
    def __init__(self, grants_cog, cog):
        self._grants = grants_cog
        self.cog = cog
        self._cog_name = cog.__class__.__name__.lower()
        self.default_perms = {}

    async def require(self, ctx, perm):
        """Raise if ctx doesn't have explicit perm."""

    def permission_allow(self, permission_name, *nodes):
        """Specify default permission -> node allow mapping.

        Only makes sense for default-deny perms.
        """
        if not hasattr(discord.Permissions, permission_name):
            raise ValueError(f"{permission_name} doesn't look like a real permission")

        nodes = {f"{self._cog_name}.{node}" for node in nodes}
        try:
            self.default_perms["permission_allow"][permission_name].update(nodes)
        except KeyError:
            try:
                self.default_perms["permission_allow"][permission_name] = set(nodes)
            except KeyError:
                self.default_perms["permission_allow"] = {
                    permission_name: set(nodes)
                }

    def guild_allow(self, *nodes):
        """Mark the nodes as default-allow.
        
        Useful if you define explicit node but want to allow by default.
        """
        nodes = {f"{self._cog_name}.{node}" for node in nodes}
        try:
            self.default_perms["guild_allow"].update(nodes)
        except KeyError:
            self.default_perms["guild_allow"] = set(nodes)


def command_implicit_node(command):
    crumbs = []
    while command.parent:
        crumbs.append(command.name)
        command = command.parent
    crumbs.append(command.name)
    if command.cog:
        crumbs.append(command.cog.__class__.__name__.lower())
    else:
        crumbs.append("bot")
    return ".".join(reversed(crumbs))


def command_implicit_restricted(command):
    return getattr(command.callback, "__dango_restricted__", False)


def command_explicit_nodes(command):
    if command.cog:
        prefix = command.cog.__class__.__name__.lower()
    else:
        prefix = "bot"
    return {
        f"{prefix}.{node}" for node in
        getattr(command.callback, "__dango_grants__", [])
    }


@dcog(depends=["JsonConfig"], pass_bot=True)
class Grants(Cog):
    def __init__(self, bot, config, jsonconfig):
        del config

        self.bot = bot
        self.jsonconfig = jsonconfig
        self._cog_contexts = {}
        jsonconfig.register(CONFIG_NAME, self.validate_grants, self.on_grants_update)
        # Note, call_once=True effectivly means can_run() doesn't use this check.
        # For the help command, this means it won't filter based on this check.
        bot.add_check(self.check_grants, call_once=False)

    def context(self, cog: commands.Cog):
        """Returns the grants handle for the cog.
        
        self.gctx = grants_cog.context(self)

        self.gctx.permission_allow("manage_server", "config.update")

        then:
        self.gctx.require("some.perm")
        """
        cog_name = cog.__class__.__name__.lower()
        try:
            return self._cog_contexts[cog_name]
        except KeyError:
            self._cog_contexts[cog_name] = GrantsContext(self, cog)
        return self._cog_contexts[cog_name]


    def cog_unload(self):
        # This is especially important since cog unload doesn't remove checks automatically
        self.bot.remove_check(self.check_grants, call_once=False)
        self.jsonconfig.unregister(CONFIG_NAME)

    async def check_grants(self, ctx):
        if not ctx.guild:
            log.debug("Blanket-allowing dm permissions")
            return True
        if ctx.author.guild_permissions.administrator:
            log.debug("Blanket-allowing server administrator all permissions")
            return True

        # Command-implicit node handling
        implicit_node = command_implicit_node(ctx.command)
        implicit_restricted = command_implicit_restricted(ctx.command)
        explicit_nodes = command_explicit_nodes(ctx.command)

        required_nodes = explicit_nodes.union([implicit_node])

        # Check explicit nodes first, since they're more likely to be denied...
        log.info("%s", implicit_node)
        
        # TODO - this is kinda messy...
        try:
            perm_config = await self.jsonconfig.get_json(ctx.guild.id, CONFIG_NAME)
        # FIXME - lmao awful
        except KeyError:
            perm_config = {}
        if ctx.command.cog:
            cog_config = self.context(ctx.command.cog).default_perms
        else:
            cog_config = {}

        # Users > Roles > Permissions > Defaults
        author_id = str(ctx.author.id)
        try:
            denied_nodes = required_nodes.intersection(perm_config["user_deny"][author_id])
            if denied_nodes:
                raise errors.CheckFailure(f"Member {ctx.author} (ID: {ctx.author.id} is denied {denied_nodes}")
        except KeyError:
            pass
        try:
            remaining_nodes = required_nodes.difference(perm_config["user_allow"][author_id])
            if not remaining_nodes:
                # All nodes are explicitly allowed, we're done here
                log.debug("All required nodes were explicitly user-allowed")
                return
            # otherwise, we still need to check for the remaining nodes:
            log.debug(f"After user_allow, {remaining_nodes} remain required")
            required_nodes = remaining_nodes
        except KeyError:
            pass

        # Roles > Permissions > Defaults
        author_roles = {str(r.id) for r in ctx.author.roles}
        try:
            roles_to_check = author_roles.intersection(perm_config["role_deny"].keys())
            for role_id in roles_to_check:
                denied_nodes = required_nodes.intersection(perm_config["role_deny"][role_id])
                if denied_nodes:
                    role = discord.utils.get(ctx.author.roles, id=int(role_id))
                    raise errors.CheckFailure(f"Members of role {role} (ID: {role.id}) are denied {denied_nodes}")
        except KeyError:
            pass

        try:
            roles_to_check = author_roles.intersection(perm_config["role_allow"].keys())
            for role_id in roles_to_check:
                remaining_nodes = required_nodes.difference(perm_config["role_allow"][role_id])
                if not remaining_nodes:
                    log.debug("All required nodes were explicitly role-allowed")
                    return
                log.debug(f"After role_allow[{role_id}], {remaining_nodes} remain required")
                required_nodes = remaining_nodes
        except KeyError:
            pass

        # Permissions > Defaults
        author_permissions = {
            perm_name for perm_name, perm_value
            in ctx.author.guild_permissions if perm_value
        }
        # Hey, we finally get into cog defaults!
        try:
            perms_to_check = author_permissions.intersection(cog_config["permission_allow"].keys())
            for perm in perms_to_check:
                default_allowed_nodes = set(cog_config["permission_allow"][perm])
                try:
                    default_allowed_nodes.difference_update(perm_config["permission_reset"][perm])
                except KeyError:
                    pass
                remaining_nodes = required_nodes.difference(default_allowed_nodes)
                if not remaining_nodes:
                    log.debug("All required nodes were explicitly permission-allowed")
                log.debug(f"After default_permission_allow[{perm}], {remaining_nodes} remain required")
                required_nodes = remaining_nodes
        except KeyError:
            pass

        # OK now custom allows... lots of copy paste here...
        # (It doesn't really make sense to deny a permission because of a discord perm, so that doesn't exist)
        try:
            perms_to_check = author_permissions.intersection(perm_config["permission_allow"].keys())
            for perm in perms_to_check:
                remaining_nodes = required_nodes.difference(perm_config["permission_allow"][perm])
                if not remaining_nodes:
                    log.debug("All required nodes were explicitly permission-allowed")
                log.debug(f"After permission_allow[{perm}], {remaining_nodes} remain required")
                required_nodes = remaining_nodes
        except KeyError:
            pass

        # Explicit defaults
        try:
            denied_nodes = required_nodes.intersection(perm_config["guild_deny"])
            if denied_nodes:
                raise errors.CheckFailure(f"{denied_nodes} is denied by default")
        except KeyError:
            pass

        try:
            remaining_nodes = required_nodes.difference(perm_config["guild_allow"])
            if not remaining_nodes:
                log.debug("All required nodes were explicitly default-allowed")
            log.debug(f"After guild_allow, {remaining_nodes} remain required")
            required_nodes = remaining_nodes
        except KeyError:
            pass

        # Cog defaults
        try:
            remaining_nodes = required_nodes.difference(cog_config["guild_allow"])
            if not remaining_nodes:
                log.debug("All required nodes were explicitly default-allowed")
            log.debug(f"After guild_allow, {remaining_nodes} remain required")
            required_nodes = remaining_nodes
        except KeyError:
            pass

        # Implicit nodes which didn't get restricted via grants.check()
        if not implicit_restricted:
            required_nodes.remove(implicit_node)

        if required_nodes:
            raise errors.CheckFailure(f"Member {ctx.author} is denied {required_nodes}")
        
        return True
    
    def validate_grants(self, full_config):
        # Idea for validation handler:
        # an "are you sure" context, similar to name disambig, for "warnings" but not invalid
        # e.g., adding a command node that doesn't exist
        if full_config is None:
            # Clearing the config is valid, sure...
            return
        for key, value in full_config.items():
            if key not in EDITABLE_KEYS:
                raise errors.BadArgument(f"unknown key {key}")

    def on_grants_update(self, value):
        pass