from dango import dcog, Cog
from discord.ext.commands import command


@dcog(depends=["A"])
class D(Cog):
    def __init__(self, config, a):
        self.a = a

    @command()
    async def D_command(self, ctx):
        pass


@dcog(depends=["B"])
class E(Cog):
    def __init__(self, config, b):
        self.b = b

    @command()
    async def E_command(self, ctx):
        pass
