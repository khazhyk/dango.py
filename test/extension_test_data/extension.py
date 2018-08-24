from dango import dcog

from .common import utils
from .common import extras

@dcog()
class UsesCommon:
    def __init__(self, config):
        self.b = utils.dummy()
