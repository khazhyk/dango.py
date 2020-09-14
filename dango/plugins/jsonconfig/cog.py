"""Allow cogs to specify configs!

Cogs specify config entries
 - name
 - validation function - called when a specific config entry is about to be edited
 - notification function - called when a specific config entry is finished editing

All editing happens through this cog.
To register, depend on the cog and use register()
*must* unload on cog unload!
To detect footgun, keep a reference to the cog, compare to bot.get_cog()!

Allow specifying json at any level, e.g.:

Full config:
`config show
{
    cog1: {}
    cog2: {}
}

`config show cog1
{}

`config show cog1.specific_option
`config update cog1.specific_option {new_json}

etc. etc.

All configs are per-guild.
If you want to do per-channel overrides, implement it as a config option??
This might be common enough that we would want to allow a channel_overrides special thing, but don't worry
about it for now. Per-channel is definitely desired for certain things though! 
 - prefixes
 - disabling commands
 - disabling bot entirely

So maybe allow registering "channel" scope config options as well, store it as a special
channel_overrides: {}
( maybe have "comments" when pretty-printing, then strip "comments" when re-parsing)

Cogs may register "complex" entries maybe??? dunno...


ALSO: FIXME/TODO/etc.
 - lets change the bot config to be a cog...
 - and instead of requiring all bots to have a __init__(config), require they depend on it!



"""
from dataclasses import dataclass
import json
import typing

from discord.ext.commands import group, errors, Converter

from dango.core import dcog, Cog
from dango.plugins import grants


"""So here's a question:

if Grants depends on JsonConfig,
but JsonConfig has commands.......
that's circular...

Solution, probably:

JsonConfigCore

then

JsonConfigEdit, depends on both core and Grants, lmao

"""

class _Json(Converter):
    """Match something which is expected to be json of sorts.

    Strips ```json, if present, and // comments.
    Usually want to use this with consume-rest style arguments!
    """

    async def convert(self, ctx, argument):
        lines = argument.strip().split("\n")

        if lines[0].startswith("```"):
            # If there's a space, discord treats this as just a line of code
            if " " in lines[0]:
                lines[0] = lines[0][3:]
            # If there's no space, this is a language specifier, delete
            else:
                lines = lines[1:]
            # Strip trailing ```
            if lines[-1].endswith("```"):
                lines[-1] = lines[-1][:-3]

        for idx in range(len(lines)):  # pylint:disable=C0200
            comment_start = lines[idx].find("//")
            if comment_start != -1:
                lines[idx] = lines[idx][:comment_start]

        return json.loads("\n".join(lines))


@dataclass
class ConfigEntry:
    # Called pre-update, to validate. *must raise on failure*
    validate: typing.Callable[[dict], None]
    # Called *after* the update was successful
    on_updated: typing.Callable[[dict], None]
    # In-memory value, if present
    cached_value: typing.Optional[dict] = None


@dcog(depends=["Database"])
class JsonConfig(Cog):
    """Registry for jsonconfig entries."""

    def __init__(self, config, db):
        del config
        self.db = db

        self._registry: typing.Dict[ConfigEntry] = {}
        super().__init__()

    def register(self, name, validate, update):
        """Register config options."""
        self._registry[name] = ConfigEntry(validate, update)

    def unregister(self, name):
        """Unregister config options."""
        del self._registry[name]

    def show_json(self, path):
        config_entry, path = self.lookup_path(path)

        if not config_entry:
            # Generate and show the "full" json
            full_json = {}
            for name in self._registry.keys():
                full_json[name] = self.show_json(name)
            return full_json
        
        curr_output = config_entry.cached_value
        if path:
            for crumb in path.split("."):
                curr_output = curr_output[crumb]
        return curr_output

    def lookup_path(self, path):
        """Returns config entry, and remaining path."""
        if not path:
            return None, ""
        split = path.split(".", maxsplit=1)

        entry = self._registry[split[0]]
        
        if not entry.cached_value:
            # TODO/FIXME - actually look something up
            entry.cached_value = {}

        if len(split) > 1:
            return entry, split[1]
        return entry, ""
    
    async def update(self, path, value):
        """Update the config to the given value.
        
        Arguments:
          path: dot-notation path to the object to be update
            (e.g., "grants.guild_deny"). In the case that
            the path goes inside of an individual config entry,
            the validation will still happen for the entire config
            entry.
          value: The new value
        """
        config_entry, path = self.lookup_path(path)

        if not path:
            config_entry.validate(value)
            # FIXME - actually update in database
            config_entry.cached_value = value
            config_entry.on_updated(config_entry.cached_value)
            return

        # path case
        crumbs = path.split(".")
        new_value = config_entry.cached_value.copy()

        editable_cursor = new_value
        for crumb in crumbs[:-1]:
            try:
                editable_cursor = editable_cursor[crumb]
            except KeyError:
                editable_cursor[crumb] = {}
                editable_cursor = editable_cursor[crumb]

        editable_cursor[crumbs[-1]] = value

        config_entry.validate(new_value)
        config_entry.cached_value = new_value
        config_entry.on_updated(config_entry.cached_value)


@dcog(depends=["Grants", "JsonConfig"])
class JsonConfigEdit(Cog):
    """Commands for editing the config."""

    def __init__(self, config, grants, jsonconfig):
        del config
        self.grants = grants
        self.jsonconfig = jsonconfig
        super().__init__()

    @group()
    async def config(self, ctx):
        pass
    
    @config.command()
    async def show(self, ctx, path=""):
        """Show the current config."""
        await ctx.send(f"```json\n{json.dumps(self.jsonconfig.show_json(path), indent=2)}```")

    @config.command()
    # FIXME - even though we imported grants, reloading it doesn't work,
    # we have to reload one, then the other.?!?!? idk, for another time
    @grants.check()
    async def update(self, ctx, path, *, value: _Json):
        """Update a sub-section of the config.

        path is required, you may not update the entire config at once.
        value must be valid json. (This means strings must be in quotes, etc.)
        """
        await self.jsonconfig.update(path, value)
        
        await ctx.send(f"```json\n{json.dumps({path:self.jsonconfig.show_json(path)}, indent=2)}```")
    
