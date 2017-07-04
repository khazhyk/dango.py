from dango import plugin


@plugin(depends=["B"])
class C:
    def __init__(self, b):
        self.b = b


@plugin()
class A:
    pass


@plugin(depends=["A"])
class B:
    def __init__(self, a):
        self.a = a
