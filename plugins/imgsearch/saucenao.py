import aiohttp


class HTTPError(Exception):

    def __init__(self, respcode, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.resp = respcode


class SauceNAO:
    """
    SauceNAO API class
    Current rate limits for free accounts seem to be:
     7 per 30 seconds
     100 per 24 hrs

    They do offer paid accounts but the limits for those are not listed.
    """

    api_base = "https://saucenao.com/search.php"

    def __init__(self, api_key):
        self.session = aiohttp.ClientSession()
        self.api_key = api_key
        self.dbmask = 0

    def __del__(self):
        self.session.close()

    def enable_source(self, *sources):
        """
        Enable the specified SauseNAOIndexes sources
        """
        for source in sources:
            self.dbmask |= source

    def disable_source(self, *sources):
        """
        Disable the specified SauseNAOIndexes sources
        """
        for source in sources:
            self.dbmask &= ~source

    async def search(self, url, limit=1):
        """
        Searches and returns a result set
        """
        async with self.session.get(self.api_base, params=dict(
                # dbmask=self.dbmask,
                db=999,
                output_type=2,  # JSON
                numres=limit,
                url=url,
                api_key=self.api_key)) as response:

            if response.status != 200:
                raise HTTPError(response.status)

            response = await response.json()
            results = [SauceNAOResult.fromResponse(
                item) for item in response.get('results', [])]

            return results


class SauceNAOResult:
    """
    Represents a result.
    """

    def __init__(self, **kargs):
        self.data = kargs['data']
        self.header = kargs['header']
        self.similarity = float(self.header['similarity'])

    def desc(self):
        """
        Returns a short textual description of this result
        """
        return str(self.data)  # TODO

    def url(self):
        """
        Returns the access URL for this result, if applicable
        """
        return None

    @staticmethod
    def fromResponse(resp):
        """
        Creates the appropriate SauceNAOResult from the result JSON
        """
        if 'pixiv_id' in resp['data']:
            return SauceNAOPixivResult(**resp)
        else:
            return SauceNAOResult(**resp)


class SauceNAOPixivResult(SauceNAOResult):
    """ Pixiv """
    """ Example:
    header: {'similarity': '95.22', 'index_id': 5, 'index_name': 'Index #5: Pixiv Images',
    'thumbnail': 'https://img1.saucenao.com/res/pixiv/3225/32258201_s.jpg?auth=IsRA2OnppN2Dc_ntns6G8Q&exp=1450755183'}
    data: {'member_id': '316240', 'member_name': 'もとみやみつき', 'pixiv_id': '32258201', 'title': '夜デートお嬢様(´□｀*)'}
    """

    def desc(self):
        return "Pixiv: {} by {}".format(self.data['title'], self.data['member_name'])

    def url(self):
        return "http://www.pixiv.net/member_illust.php?mode=medium&illust_id={}".format(self.data['pixiv_id'])
