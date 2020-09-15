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
import asyncio
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
class ConfigRegEntry:
    # Called pre-update, to validate. *must raise on failure*
    validate: typing.Callable[[dict], None]
    # Called *after* the update was successful
    on_updated: typing.Callable[[dict], None]


@dcog(depends=["Database"])
class JsonConfig(Cog):
    """Registry for jsonconfig entries."""

    def __init__(self, config, db):
        del config
        self.db = db
        self.db.hold()

        self._registry: typing.Dict[ConfigRegEntry] = {}
        self._guild_configs = {}
        super().__init__()

    def cog_unload(self):
        self.db.unhold()

    async def _lookup_guild_config(self, guild_id: int):
        """Lookup guild config, if it exists.
        
        We cache config results forever, presuming no two shards
        operate on the same guild at the same time.
        """
        try:
            return self._guild_configs[guild_id]
        except KeyError:
            pass
        async with self.db.acquire() as conn:
            res = await conn.fetchrow(
                "SELECT * FROM jsonconfig WHERE guild_id = $1", guild_id
            )
            if res:
                guild_config = json.loads(res["data"])
            else:
                guild_config = {}
            self._guild_configs[guild_id] = guild_config
            return guild_config

    async def _update_guild_config(self, guild_id: int, data: dict):
        """Upsert the guild config. Presumes it's valid."""
        # This might be redundant??? Since it's a dict we might end up editing in place...
        self._guild_configs[guild_id] = data
        async with self.db.acquire() as conn:
            await conn.execute(
                "INSERT INTO jsonconfig (guild_id, data) "
                "VALUES ($1, $2) "
                "ON CONFLICT (guild_id) DO UPDATE SET data = $2",
                guild_id, json.dumps(data)
            )

    def register(self, name, validate, update):
        """Register config options."""
        self._registry[name] = ConfigRegEntry(validate, update)

    def unregister(self, name):
        """Unregister config options."""
        del self._registry[name]

    async def lookup_path_entry(self, guild_id: int, path):
        """Lookup config entry, dict, remaining path."""
        guild_config = await self._lookup_guild_config(guild_id)

        split = path.split(".", maxsplit=1)

        entryname = split[0]

        self._registry.__getitem__(entryname)
        # We avoid assigning into the dict here in case we don't end up
        # changing it, so we don't pollute empty dicts into the config
        entryvalue = guild_config.get(entryname, {})

        if len(split) > 1:
            return entryname, entryvalue, split[1]
        return entryname, entryvalue, ""

    async def update_path_entry(self, guild_id: int, entry_name: str, value: dict):
        """Validate and store."""
        self._registry[entry_name].validate(value)
        guild_config = await self._lookup_guild_config(guild_id)
        guild_config[entry_name] = value
        await self._update_guild_config(guild_id, guild_config)
        self._registry[entry_name].on_updated(value)
    
    async def get_json(self, guild_id, path):
        """Get json given by path.
        
        TODO - do something for placeholder shit, like:
        {
            // Description if it exists?
            "grants": {
                // For reference only, not editable
                default_guild_deny: ["tag.manage_others"],
                // For reference only, not editable
                default_guild_allow: ["tag.tag", "tag.tag.create", "tag.tag.edit"]
                // Permissions not granted for everyone
                "guild_deny": [],
                // Permissions allowed for everyone
                "guild_deny": []
            }
        }
        """
        guild_config = await self._lookup_guild_config(guild_id)
        cursor = guild_config
        if path:
            for crumb in path.split("."):
                cursor = cursor[crumb]
        return cursor

    async def update(self, guild_id: int, path, value):
        """Update the config to the given value.
        
        Arguments:
          path: dot-notation path to the object to be update
            (e.g., "grants.guild_deny"). In the case that
            the path goes inside of an individual config entry,
            the validation will still happen for the entire config
            entry.
          value: The new value
        """
        entry_name, old_config, path = await self.lookup_path_entry(guild_id, path)

        if path:
            new_config = old_config.copy()
            editable_cursor = new_config
            crumbs = path.split(".")
            for crumb in crumbs[:-1]:
                try:
                    editable_cursor = editable_cursor[crumb]
                except KeyError:
                    editable_cursor[crumb] = {}
                    editable_cursor = editable_cursor[crumb]
            editable_cursor[crumbs[-1]] = value
        else:
            new_config = value

        await self.update_path_entry(guild_id, entry_name, new_config)


@dcog(depends=["Grants", "JsonConfig"])
class JsonConfigEdit(Cog):
    """Commands for editing the config."""

    def __init__(self, config, grants_cog, jsonconfig):
        del config
        self._grants = grants_cog
        self._jsonconfig = jsonconfig
        super().__init__()

    @group()
    async def config(self, ctx):
        pass
    
    @config.command()
    async def show(self, ctx, path=""):
        """Show the current config."""
        await ctx.send(f"```json\n{json.dumps(await self._jsonconfig.get_json(ctx.guild.id, path), indent=2)}```")

    @config.command()
    # FIXME - even though we imported grants, reloading it doesn't work,
    # we have to reload one, then the other.?!?!? idk, for another time
    @grants.check()
    async def update(self, ctx, path, *, value: _Json):
        """Update a sub-section of the config.

        path is required, you may not update the entire config at once.
        value must be valid json. (This means strings must be in quotes, etc.)
        """
        await self._jsonconfig.update(ctx.guild.id, path, value)
        
        await ctx.send(f"```json\n{json.dumps({path:await self._jsonconfig.get_json(ctx.guild.id, path)}, indent=2)}```")
    
