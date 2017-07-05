import asyncio
import logging
import os
from watchdog import events

log = logging.getLogger(__name__)


def _module_name(event):
    return module_name(event.src_path)


def module_name(path):
    """Returns module name if this is likely a plugin.

    Two types of plugins:
        - *.py in the plugins/ directory
            - Simply deteched if it's a direct child of our plugin
        - folders in the plugins/ directory
            - A change to any file in a subdir should reload entire module.
    """
    path = os.path.normpath(path)
    path, ext = os.path.splitext(path)
    parts = path.split(os.sep)

    # Ignore plugins/ and plugins/__init__.py
    if len(parts) == 1 or parts[1] == "__init__":
        return

    if ext == '.py' or os.path.exists(os.path.join(path, '__init__.py')):
        return ".".join(parts[:2])  # plugins.lib


class PluginDirWatchdog(events.FileSystemEventHandler):

    def __init__(self, bot):
        self.bot = bot
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
        except:
            log.exception("Failed to reload! %s", mod_to_reload)

    def on_created(self, event):
        mod_to_reload = _module_name(event)
        if mod_to_reload:
            log.info("Detected creation of %s, loading...", event.src_path)
            self._call(self._try_reload(mod_to_reload))

    def on_deleted(self, event):
        mod_to_reload = _module_name(event)
        if mod_to_reload:
            log.info("Detected deletion of %s, unloading...", event.src_path)
            self._call(self._unload(mod_to_reload))

    def on_modified(self, event):
        mod_to_reload = _module_name(event)
        if mod_to_reload:
            log.info("Detected change to %s, reloading...", event.src_path)
            self._call(self._try_reload(mod_to_reload))

    def on_moved(self, event):
        pass
