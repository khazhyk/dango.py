import asyncio
import logging
import os
import sys
import importlib
from watchdog import events
from watchdog import observers

from . import config

log = logging.getLogger(__name__)


class PluginDirWatchdog(events.FileSystemEventHandler):

    def __init__(self, bot, module_lookup):
        self.bot = bot
        self.module_lookup = module_lookup
        super().__init__()

    def _call(self, coro):
        fut = asyncio.run_coroutine_threadsafe(
            coro,
            loop=self.bot.loop)
        return fut.result()

    async def _unload(self, mod_to_unload):
        self.bot.unload_extension(mod_to_unload)

    async def _try_reload(self, mod_to_reload):
        try:
            self.bot.unload_extension(mod_to_reload)
            self.bot.load_extension(mod_to_reload)
        except BaseException:
            log.exception("Failed to reload! %s", mod_to_reload)

    def on_created(self, event):
        mod_to_reload = self.module_lookup(event)
        if mod_to_reload:
            log.info("Detected creation of %s, loading...", event.src_path)
            self._call(self._try_reload(mod_to_reload))

    def on_deleted(self, event):
        mod_to_reload = self.module_lookup(event)
        if mod_to_reload:
            log.info("Detected deletion of %s, unloading...", event.src_path)
            self._call(self._unload(mod_to_reload))

    def on_modified(self, event):
        mod_to_reload = self.module_lookup(event)
        if mod_to_reload:
            log.info("Detected change to %s, reloading...", event.src_path)
            self._call(self._try_reload(mod_to_reload))

    def on_moved(self, event):
        pass


class WatchdogExtensionLoader:
    """File watchdog based extension loader.

    This is mostly made for people running a bot where the plugins are in the
    local directory or something similar. Watch the module directory for changes
    and reload the modules if they change. discord.py handles cog/etc.
    unloading, we just call unload_extension/load_extension.
    """
    def __init__(self, bot):
        self.bot = bot
        self._watches = {}
        self._observer = None

    def start(self):
        self._observer = observers.Observer()
        for dir_, handler in self._watches.items():
            self._observer.schedule(handler, dir_, recursive=True)
        self._observer.start()

    def close(self):
        if self._observer:
            self._observer.close()
        self._observer = None

    def watch_spec(self, plugin_spec):
        """Watch the plugin spec for changes.

        Arguments
        ---------
        plugin_spec: str
            "some.module" - Load this module, watch changes to it and below.
            "module.*" - Load all submodules in this module, using a directory
                listing. Will only go one level (e.g. will load_ext 
                path.to.module but not path.to.module.submodule)

        Raises
        ------
        ValueError if plugin_spec overlaps with existing spec.
        """

        module_parts = plugin_spec.split('.')

        exts_to_load = []

        if module_parts[-1] == "*":
            plugin_spec = ".".join(module_parts[:-1])
            if plugin_spec in sys.modules:
                log.warning("%s is already loaded by some outside source, we "
                            "may not be able to unload it!", plugin_spec)

            mod = importlib.import_module(plugin_spec)

            if not mod.__spec__.submodule_search_locations:
                raise ValueError("There's no submodules to watch here...")

            watched_location = os.path.normpath(mod.__spec__.submodule_search_locations[0])
            def _module_name(src_path):
                assert src_path.startswith(watched_location)

                subpath = src_path[len(watched_location)+1:]
                subparts = subpath.split(os.sep)

                if not subparts or not subparts[0]:
                    return

                modname, ext = os.path.splitext(subparts[0])

                if ext == ".py":
                    return ".".join([plugin_spec, modname])
                if os.path.exists(os.path.join(watched_location, modname, '__init__.py')):
                    return ".".join([plugin_spec, modname])

            for item in os.listdir(watched_location):
                lib = _module_name(os.path.join(watched_location, item))
                if lib:
                    try:
                        self.bot.load_extension(lib)
                    except config.InvalidConfig:
                        log.error("Could not load %s due to invalid config!", lib)

            self._watches[watched_location] = PluginDirWatchdog(self.bot, lambda e: _module_name(e.src_path))
        else:
            if plugin_spec in sys.modules:
                log.warning("%s is already loaded by some outside source, we "
                            "may not be able to unload it!", plugin_spec)

            mod = importlib.import_module(plugin_spec)

            # We can only schedule watchs on directories.
            if mod.__spec__.submodule_search_locations:
                watched_location = mod.__spec__.submodule_search_locations[0]
                def module_name(event):
                    return plugin_spec
            else:
                watched_file = mod.__spec__.origin
                def module_name(event):
                    if event.src_path != watched_file:
                        return
                    return plugin_spec
                watched_location = os.path.split(mod.__spec__.origin)[0]
            self._watches[watched_location] = PluginDirWatchdog(self.bot, module_name)
            try:
                self.bot.load_extension(plugin_spec)
            except config.InvalidConfig:
                log.error("Could not load %s due to invalid config!", plugin_spec)


