from dango import plugin


@plugin(depends=["A"])
class D:
    def __init__(self, a):
        self.a = a


@plugin(depends=["B"])
class E:
    def __init__(self, b):
        self.b = b
