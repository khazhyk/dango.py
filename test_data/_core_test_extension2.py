from dango import dcog


@dcog(depends=["A"])
class D:
    def __init__(self, a):
        self.a = a


@dcog(depends=["B"])
class E:
    def __init__(self, b):
        self.b = b
