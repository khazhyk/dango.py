from dango import dcog
from discord.ext.commands import command


@dcog(depends=["B"])
class C:
    def __init__(self, config, b):
        self.b = b

    @command()
    async def C_command(self, ctx):
        pass


@dcog()
class A:
    def __init__(self, config):
        pass

    @command()
    async def A_command(self, ctx):
        pass


@dcog(depends=["A"])
class B:
    def __init__(self, config, a):
        self.a = a

    @command()
    async def B_command(self, ctx):
        pass
