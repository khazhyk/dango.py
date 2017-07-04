# dango

Discord.py commands ext extensions + plugin collection.

## TODO

- [x] Automatically prevent @everyone, @here, etc. on all outbound messages
    - [x] Automatically upload too-large messages to 0bin etc.
    - [ ] Need to do tracked message sending for `blame, stats, etc.
    - [ ] * Hmm, this doesn't apply to, e.g., author.send, etc., probably OK.
- [ ] Embed wrapper for the info stuff.
    - [ ] Paginated for stuff like socket_events
    - [ ] The wrapper also works for classic text-based k.v. display.
- [ ] New/better RPC system, multi-shard aware.
    - [ ] Rolling restart system (maybe)
- [ ] Look into using `watchdog` for watch_plugin_dir
    - [ ] For this we need to be able to reload plugins, even if we depend on them.
    - [ ] Plugin dependency system?
    - [ ] Detect if dango/core/whatever changes. If we have a change outside of
        plugins, we likely need a full restart, not just a reload.


## Testing
python -m unittest discover -p "*_test.py"

## Plugin system

- Cogs marked with @plugin are loaded on extension load.
- These cogs are added to the bot via add_plugin(cls)
    - If a plugin has no dependencies, we can load it immediately.
    - If all a plugin's dependencies are loaded, we can load it immediately
    - If at least one of a plugin's dependencies are unloaded, defer it. On
        plugin load, we can check if our dependencies are now loaded, and if so
        load ourselves.
    - For debugging, we can call done_loading once we thing everything should
        be loaded, and warn if we see pending plugins. (This could be due to
        missing plugin, circular dependencies, etc.)