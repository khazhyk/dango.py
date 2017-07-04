from dango import dcog


@dcog(depends=["B"])
class C:
    def __init__(self, b):
        self.b = b


@dcog()
class A:
    pass


@dcog(depends=["A"])
class B:
    def __init__(self, a):
        self.a = a
