from dango import dcog
from discord.ext.commands import command


@dcog(depends=["UsesCommon"])
class UsesUsesCommon:
    def __init__(self, config, uc):
        self.uc = uc

    @command()
    async def a_command_here(self, ctx):
        pass

