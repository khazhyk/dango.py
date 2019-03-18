from dango import dcog, Cog

from .common import utils
from .common import extras

@dcog()
class UsesCommon(Cog):
    def __init__(self, config):
        self.b = utils.dummy()
