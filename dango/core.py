import collections
import datetime
import importlib
import logging
import os
import io
import sys
import re

import discord
from discord.ext import commands
from discord.utils import cached_property

from . import config
from . import extensions
from . import utils

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

class Cog(commands.Cog):
    pass


def _is_submodule(parent, child):
    return parent == child or child.startswith(parent + ".")


def force_unload(name):
    if name in sys.modules:
        del sys.modules[name]
    for module in list(sys.modules.keys()):
        if _is_submodule(name, module):
            del sys.modules[module]



PluginDesc = collections.namedtuple("PluginDesc", "depends pass_bot")
CogDesc = collections.namedtuple("PluginDesc", "load_time")


class DangoContext(commands.Context):

    async def send(self, content=None, file=None, files=None, *args, **kwargs):
        """Override for send to add message filtering."""
        # TODO - this maybe shouldn't be in dango
        file_to_send = None
        if content:
            content = str(content)
            content = re.sub("@everyone", "@\u200beveryone", content, flags=re.IGNORECASE)
            content = re.sub("@here", "@\u200bhere", content, flags=re.IGNORECASE)

            if len(content) > 2000:
                text_file = io.BytesIO(content.encode('utf8'))
                content = None
                file_to_send = discord.File(fp=text_file, filename="message.txt")

        if file_to_send:
            if file:
                files = [file, file_to_send]
            elif files:
                files.append(file_to_send)
            else:
                files = [file_to_send]

        sent_message = await super().send(content, *args, file=file, files=files, **kwargs)
        self.bot.dispatch("dango_message_sent", sent_message, self)
        return sent_message

    def __repr__(self):
        return "<DangoContext message={0.message!r} message.content={0.message.content!r} channel={0.channel!r} prefix={0.prefix!r} command={0.command!r} invoked_with={0.invoked_with!r}>".format(self)

class DangoBotBase(commands.bot.BotBase):

    def __init__(self, *args, conf="config.yml", intents=discord.Intents.all(), **kwargs):
        self._config = config.FileConfiguration(conf)
        self._config.load()
        cgroup = self._config.root
        try:
            self.prefix = cgroup.register("prefix", default="test ")
            self.token = cgroup.register("token")
            self.plugins = cgroup.register("plugins", default="dango.plugins.*")
            self.waaai_api_key = cgroup.register("waaai_api_key")
            self._is_bot = cgroup.register("bot", default=True).value
        finally:
            # Raise and fail to start on invalid core config
            self._config.save()

        self._loader = extensions.WatchdogExtensionLoader(self)
        self._dango_unloaded_cogs = {}
        super().__init__(self.prefix.value, *args, self_bot=not self._is_bot, intents=intents, **kwargs)

    async def start(self, *args, **kwargs):
        if isinstance(self.plugins(), str):
            await self._loader.watch_spec(self.plugins())
        else:
            for plugin_dir in self.plugins():
                await self._loader.watch_spec(plugin_dir)
        self._loader.start()
        await super().start(self.token.value, *args, **kwargs)

    async def on_error(self, event, *args, **kwargs):
        log.exception(
            "Unhandled exception in %s\nargs: %s\nkwargs: %s\n",
            event, args, kwargs)

    def get_context(self, message):
        return super().get_context(message, cls=DangoContext)

    async def add_cog(self, cls):
        """Tries to load a cog.

        If not all dependencies are loaded, will defer until they are.
        """
        desc = getattr(cls, PLUGIN_DESC, None)
        if not desc:
            log.debug("Loading cog %s", cls)
            return await super().add_cog(cls)

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
        await super().add_cog(cog)
        setattr(cog, COG_DESC, CogDesc(datetime.datetime.utcnow()))
        log.debug("Loaded dcog %s.%s", cls.__module__, cls.__name__)

        # Try loading previously unloaded plugins.
        unloaded_plugins = self._dango_unloaded_cogs
        self._dango_unloaded_cogs = {}
        for plugin in unloaded_plugins.values():
            await self.add_cog(plugin)

    async def remove_cog(self, name, remove=True):
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
            await self.unload_cog_deps(cog)
            self._config.root.remove_group(utils.snakify(name))

        await super().remove_cog(name)
        log.debug("Unloaded dcog %s", name)

    async def unload_cog_deps(self, unloading_cog):
        for cog_name, cog_inst in self.cogs.copy().items():
            desc = getattr(cog_inst, PLUGIN_DESC, None)
            if not desc:
                continue

            if type(unloading_cog).__name__ in desc.depends:
                await self.remove_cog(cog_name, remove=False)

    async def load_extension(self, name):
        """Override load extension to auto-detect dcogs."""
        if name in self.extensions:
            return

        log.info("Loading extension %s", name)
        # Just in case we previously failed to unload this module, force unload it
        force_unload(name)
        lib = importlib.import_module(name)

        for item in dir(lib):  # TODO - inspect.members
            val = getattr(lib, item)
            if isinstance(val, type) and hasattr(val, PLUGIN_DESC):
                await self.add_cog(val)

        setup = getattr(lib, 'setup', None)
        if setup:
            await discord.utils.maybe_coroutine(setup, self)

        self._BotBase__extensions[name] = lib

    def unload_extension(self, name):
        """Override unload extension to cleanup cog dependencies."""
        removelist = []
        for k, v in self._dango_unloaded_cogs.items():
            if _is_submodule(name, v.__module__):
                removelist.append(k)
        for k in removelist:
            del self._dango_unloaded_cogs[k]

        return super().unload_extension(name)

    async def close(self):
        self._loader.close()
        return await super().close()


class DangoAutoShardedBot(DangoBotBase, discord.AutoShardedClient):
    pass


class DangoBot(DangoBotBase, discord.Client):
    pass
