from dango import dcog, Cog
from .common import utils

@dcog(depends=["UsesCommon"])
class UsesCommonAlso(Cog):
    def __init__(self, config, uc):
        self.uc = uc
        self.b = utils.dummy()
