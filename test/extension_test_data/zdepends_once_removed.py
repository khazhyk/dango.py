"""This cog is removed both by cog dependency and extension dependency.

We have to make sure we aren't double-removing/double-adding.
"""

from dango import dcog
from discord.ext.commands import command
from .common import utils

@dcog(depends=["UsesUsesCommon"])
class UsesUsesUsesCommon:
    def __init__(self, config, uc):
        self.uc = uc
        self.b =  utils.dummy()

    @command()
    async def a_command(self, ctx):
        pass
