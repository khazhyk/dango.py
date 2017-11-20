from dango import dcog


@dcog()
class Res:
    """Resources."""

    def __init__(self, config):
        self.dir = config.register("dir")
