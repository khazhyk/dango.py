from dango import dcog
from discord.ext.commands import command

@dcog()
class SubModule:
    def __init__(self, config):
        pass

    @command()
    async def SubModule_command(self, ctx):
        pass
