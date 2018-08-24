from dango import dcog
from .common import utils

@dcog(depends=["UsesCommon"])
class UsesCommonAlso:
    def __init__(self, config, uc):
        self.uc = uc
        self.b = utils.dummy()
