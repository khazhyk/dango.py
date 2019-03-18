from dango import dcog, Cog


@dcog()
class Res(Cog):
    """Resources."""

    def __init__(self, config):
        self.dir = config.register("dir")
