from dango import dcog, Cog
from discord.ext.commands import command


@dcog(depends=["B"])
class C(Cog):
    def __init__(self, config, b):
        self.b = b

    @command()
    async def C_command(self, ctx):
        pass


@dcog()
class A(Cog):
    def __init__(self, config):
        pass

    @command()
    async def A_command(self, ctx):
        pass


@dcog(depends=["A"])
class B(Cog):
    def __init__(self, config, a):
        self.a = a

    @command()
    async def B_command(self, ctx):
        pass
