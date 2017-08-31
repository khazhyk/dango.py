# dango

Discord.py commands ext extensions + plugin collection.

## TODO

- [x] Automatically prevent @everyone, @here, etc. on all outbound messages
    - [x] Automatically upload too-large messages to 0bin etc.
    - [x] Need to do tracked message sending for `blame, stats, etc.
    - [ ] * Hmm, this doesn't apply to, e.g., author.send, etc., probably OK.
- [ ] Embed wrapper for the info stuff.
    - [ ] Paginated for stuff like socket_events
    - [ ] The wrapper also works for classic text-based k.v. display.
- [ ] New/better RPC system, multi-shard aware.
    - [ ] Rolling restart system
- [x] Look into using `watchdog` for watch_plugin_dir
    - [x] For this we need to be able to reload plugins, even if we depend on them.
    - [x] Plugin dependency system?
    - [ ] Detect if dango/core/whatever changes. If we have a change outside of
        plugins, we likely need a full restart, not just a reload.
- [x] Config system
    - [x] Allow plugins/cogs to declare config elements w/ defaults
    - [x] Populate config file on cog load.
- [x] Generic attribute system
    - [x] Implement as a cog on top of Database + Redis
- [ ] Make d.py extension loading transactional - unload extensions if they fail
        to load all the way. (This will fix issues where when an extension
        fails to load, you will no longer be able to reload it because it won't
        be in bot.extensions)

- [ ] Port over existing functionality
    - [ ] Server/channel configuration
    - [ ] Overwatch
    - [x] imgsearch
    - [x] last seen, username, nickname tracking
    - [ ] carbonitex reporting
    - [ ] meme posts etc.
    - [x] userinfo etc.
    - [ ] socket debug status
    - [ ] misc
    - [ ] mod commands
    - [x] osu
    - [ ] pmmentions
        - [ ] add highlight regex/etc. features

- Handle exceptions in batch update task

asyncpg.exceptions.DeadlockDetectedError: deadlock detected
DETAIL:  Process 21424 waits for ShareLock on transaction 2173850; blocked by process 14812.
Process 14812 waits for ShareLock on transaction 2173849; blocked by process 21424.

## Testing
pytest

## Plugin system

- Cogs marked with @dcog are loaded on extension load.
- These cogs are added to the bot via add_plugin(cls)
    - If a plugin has no dependencies, we can load it immediately.
    - If all a plugin's dependencies are loaded, we can load it immediately
    - If at least one of a plugin's dependencies are unloaded, defer it. On
        plugin load, we can check if our dependencies are now loaded, and if so
        load ourselves.
    - For debugging, we can call done_loading once we thing everything should
        be loaded, and warn if we see pending plugins. (This could be due to
        missing plugin, circular dependencies, etc.)