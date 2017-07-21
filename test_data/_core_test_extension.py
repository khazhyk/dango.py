from dango import dcog


@dcog(depends=["B"])
class C:
    def __init__(self, config, b):
        self.b = b


@dcog()
class A:
    def __init__(self, config):
        pass


@dcog(depends=["A"])
class B:
    def __init__(self, config, a):
        self.a = a
