import collections
import datetime
import importlib
import logging
import os
import re

import discord
from discord.ext import commands
from discord.utils import cached_property
from watchdog import observers

from . import config
from . import plugin_watchdog
from . import utils
from . import waaai
from . import zerobin

log = logging.getLogger(__name__)

PLUGIN_DESC = "__dango_plugin_desc__"
COG_DESC = "__dango_cog_desc__"


def dcog(depends=None, pass_bot=False):
    def real_decorator(cls):
        setattr(cls, PLUGIN_DESC, PluginDesc(
            depends=depends or [],
            pass_bot=pass_bot
        ))
        return cls
    return real_decorator


PluginDesc = collections.namedtuple("PluginDesc", "depends pass_bot")
CogDesc = collections.namedtuple("PluginDesc", "load_time")


class DangoContext(commands.Context):

    async def send(self, content=None, *args, **kwargs):
        """Override for send to add message filtering."""
        # TODO - this maybe shouldn't be in dango
        if content:
            content = re.sub("@everyone", "@\u200beveryone", content, flags=re.IGNORECASE)
            content = re.sub("@here", "@\u200bhere", content, flags=re.IGNORECASE)

            if len(content) > 2000:
                try:
                    zbin_url = await zerobin.upload_zerobin(content)
                    waaai_url = await waaai.send_to_waaai(
                        zbin_url, self.bot.waaai_api_key())
                    content = "Content too long: %s" % waaai_url
                except BaseException:  # TODO
                    log.exception("Exception when uploading to zerobin...")
                    # text_file = io.BytesIO(content.encode('utf8'))
                    content = "Way too big..."

        sent_message = await super().send(content, *args, **kwargs)
        self.bot.dispatch("dango_message_sent", sent_message, self)
        return sent_message

    def __repr__(self):
        return "<DangoContext message={0.message!r} message.content={0.message.content!r} channel={0.channel!r} prefix={0.prefix!r} command={0.command!r} invoked_with={0.invoked_with!r}>".format(self)

class DangoBotBase(commands.bot.BotBase):

    def __init__(self, *args, conf="config.yml", **kwargs):
        self._config = config.FileConfiguration(conf)
        self._config.load()
        cgroup = self._config.root
        try:
            self.prefix = cgroup.register("prefix", default="test ")
            self.token = cgroup.register("token")
            self.plugins = cgroup.register("plugins", default="plugins")
            self.waaai_api_key = cgroup.register("waaai_api_key")
        finally:
            # Raise and fail to start on invalid core config
            self._config.save()

        self._dango_unloaded_cogs = {}
        super().__init__(self.prefix.value, *args, **kwargs)

    def run(self):
        self.watch_plugin_dir(self.plugins.value)
        super().run(self.token.value)

    async def on_error(self, event, *args, **kwargs):
        log.exception(
            "Unhandled exception in %s\nargs: %s\nkwargs: %s\n",
            event, args, kwargs)

    def get_context(self, message):
        return super().get_context(message, cls=DangoContext)

    def add_cog(self, cls):
        """Tries to load a cog.

        If not all dependencies are loaded, will defer until they are.
        """
        desc = getattr(cls, PLUGIN_DESC, None)
        if not desc:
            log.debug("Loading cog %s", cls)
            return super().add_cog(cls)

        depends = [self.get_cog(name) for name in desc.depends]
        if not all(depends):
            self._dango_unloaded_cogs[cls.__name__] = cls
            return

        self._config.load()
        cgroup = self._config.root.add_group(utils.snakify(cls.__name__))

        depends.insert(0, cgroup)
        if desc.pass_bot:
            depends.insert(0, self)

        try:
            cog = cls(*depends)
        except config.InvalidConfig:
            raise
        finally:
            self._config.save()
        super().add_cog(cog)
        setattr(cog, COG_DESC, CogDesc(datetime.datetime.utcnow()))
        log.debug("Loaded dcog %s.%s", cls.__module__, cls.__name__)

        # Try loading previously unloaded plugins.
        unloaded_plugins = self._dango_unloaded_cogs
        self._dango_unloaded_cogs = {}
        for plugin in unloaded_plugins.values():
            self.add_cog(plugin)

    def remove_cog(self, name, remove=True):
        """Unloads a cog.

        Name of a cog must be it's class name.
        If another cog depends on this one, unload but do not remove it.
        """
        cog = self.cogs.get(name, None)

        if remove:
            if name in self._dango_unloaded_cogs:
                del self._dango_unloaded_cogs[name]
        elif cog:
            self._dango_unloaded_cogs[name] = type(cog)

        if not cog:
            return

        if hasattr(cog, PLUGIN_DESC):
            self.unload_cog_deps(cog)

        self._config.root.remove_group(utils.snakify(name))
        super().remove_cog(name)
        log.debug("Unloaded dcog %s", name)

    def unload_cog_deps(self, unloading_cog):
        for cog_name, cog_inst in self.cogs.copy().items():
            desc = getattr(cog_inst, PLUGIN_DESC, None)
            if not desc:
                continue

            if type(unloading_cog).__name__ in desc.depends:
                self.remove_cog(cog_name, remove=False)

    def load_extension(self, name):
        """Override load extension to auto-detect dcogs.

        Note: We do not override unload_extension, as it works fine.
        """
        if name in self.extensions:
            return

        log.info("Loading extension %s", name)
        lib = importlib.import_module(name)

        for item in dir(lib):  # TODO - inspect.members
            val = getattr(lib, item)
            if isinstance(val, type) and hasattr(val, PLUGIN_DESC):
                self.add_cog(val)

        setup = getattr(lib, 'setup', None)
        if setup:
            setup(self)

        self.extensions[name] = lib

    def watch_plugin_dir(self, dire):
        # TODO - story is kind of icky for folder modules - we need to import
        # cogs into __init__.py, not much better than setup() in __init__.py
        for item in os.listdir(dire):
            lib = plugin_watchdog.module_name(os.path.join(dire, item))
            if lib:
                try:
                    self.load_extension(lib)
                except config.InvalidConfig:
                    log.error("Could not load %s due to invalid config!", lib)

        if self._dango_unloaded_cogs:
            log.warning(
                "Some plugins were unable to load due to missing deps: %s",
                ",".join("%s.%s" % (c.__module__, c.__name__)
                         for c in self._dango_unloaded_cogs.values()))
        self.watchdog_dir(dire)

    @cached_property
    def observer(self):
        ob = observers.Observer()
        ob.start()
        return ob

    async def close(self):
        self.observer.stop()
        return await super().close()

    def watchdog_dir(self, dire):
        self.observer.schedule(
            plugin_watchdog.PluginDirWatchdog(self), dire, recursive=True)


class DangoAutoShardedBot(DangoBotBase, discord.AutoShardedClient):
    pass


class DangoBot(DangoBotBase, discord.Client):
    pass
