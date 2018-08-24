import asyncio
import collections
import logging
import os
import time
import types
import threading
import sys
import importlib
from watchdog import events
from watchdog import observers

from . import config

log = logging.getLogger(__name__)


def _is_submodule(parent, child):
    return parent == child or child.startswith(parent + ".")


class ModuleDirWatchdog(events.FileSystemEventHandler):

    def __init__(self, register, module_lookup, loop=None):
        self._register = register
        self.module_lookup = module_lookup
        self.loop = loop or asyncio.get_event_loop()
        super().__init__()

    def _call(self, coro):
        fut = asyncio.run_coroutine_threadsafe(
            coro,
            loop=self.loop)
        return fut.result()

    async def _unload(self, mod_to_unload):
        self._register.unload_extension(mod_to_unload)

    async def _try_reload(self, mod_to_reload):
        try:
            self._register.reload_extension(mod_to_reload)
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
        self._register = ExtensionDependencyRegister(bot)
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

            self._register.set_reloadable(plugin_spec)
            mod = importlib.import_module(plugin_spec)

            if not mod.__spec__.submodule_search_locations:
                raise ValueError("There's no submodules to watch here...")

            watched_location = os.path.normpath(list(mod.__spec__.submodule_search_locations)[0])
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
                        self._register.load_extension(lib)
                    except config.InvalidConfig:
                        log.error("Could not load %s due to invalid config!", lib)

            self._watches[watched_location] = ModuleDirWatchdog(self._register, lambda e: _module_name(e.src_path))
        else:
            if plugin_spec in sys.modules:
                log.warning("%s is already loaded by some outside source, we "
                            "may not be able to unload it!", plugin_spec)

            self._register.set_reloadable(plugin_spec)
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
            self._watches[watched_location] = ModuleDirWatchdog(self._register, module_name)
            try:
                self._register.load_extension(plugin_spec)
            except config.InvalidConfig:
                log.error("Could not load %s due to invalid config!", plugin_spec)


class ExtensionDependencyRegister:
    """Load/unload extensions, managing dependencies.

    Two main types of deps:
     - cog injection (this is @dcog(depends=["AnotherCog"])). For this we need
      to instanciate the depended on cog and pass it in the constructor. Then
      store the dependency and manage extension reloads. This is done in the
      bot for now because I need to fix the config loading ickiness...
     - extension imports. For this all we really need to do is store the
      dependencies and manage extension reloads.

    Needs a registry of "reloadable" modules - generally those which are
    watched are reloadable.
    """

    def __init__(self, bot):
        self.bot = bot
        self._deps = collections.defaultdict(set)
        self._reloadable = []

    def set_reloadable(self, base):
        """Mark a base module and it's submodules as reloadable."""
        self._reloadable.append(base)

    def load_extension(self, name):
        """Load an extension and track it's dependencies.

        Extension "curious" imports "common", so add a dependency.
        self._deps["common"].append("curious")
        """

        self.bot.load_extension(name)  # Assume all goes well...
        lib = self.bot.extensions[name]  # Will throw if it didn't go well anyways RIP

        for item in dir(lib):  # TODO - inspect.members
            val = getattr(lib, item)

            if isinstance(val, types.ModuleType):
                for r in self._reloadable:
                    if _is_submodule(r, val.__spec__.name):
                        log.info("module %s imports %s which is probably reloadable", name, val)
                        self._deps[name].add(val.__spec__.name)
                        break
            elif hasattr(val, "__module__"):  # TODO
                pass

    def unload_extension(self, name, unload_dependants=False, unloaded_extensions=None):
        """Unload an extension. Do not unload dependants.

        It's not garunteed an extension will be re-loaded, just leave
        old extensions in place.

        Returns a list of all unloaded extensions, in dependency order.
        """
        log.info("Preparing to unload %s", name)

        unloaded_extensions = unloaded_extensions or []
        unloaded_extensions.append(name)

        if unload_dependants:
            for key, deplist in self._deps.items():
                if key == name:  # Don't need to unload ourselves
                    continue
                if key in unloaded_extensions:  # Already unloading
                    continue
                for dep in deplist:
                    if _is_submodule(name, dep):
                        log.info("Unloading %s should unload %s since it needs %s", name, key, dep)

                        self.unload_extension(
                            key, unload_dependants=True,
                            unloaded_extensions=unloaded_extensions)
                        break

        log.info("Finally unloading %s", name)
        self.bot.unload_extension(name)
        return unloaded_extensions

    def reload_extension(self, name):
        """Reload an extension and it's dependants.

        Unloading extension "common", check _deps and unload it's dependants
        first. (recursively etc.)

        """
        unloaded_deps = self.unload_extension(name, unload_dependants=True)
        for unloaded_dep in unloaded_deps:
            self.load_extension(unloaded_dep)
        return unloaded_deps
