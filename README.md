# dango

Discord.py commands ext extensions + plugin collection.

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
