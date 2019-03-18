from dango import dcog, Cog
from discord.ext.commands import command

@dcog()
class SubModule(Cog):
    def __init__(self, config):
        pass

    @command()
    async def SubModule_command(self, ctx):
        pass
