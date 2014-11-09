import json
from tornado import gen
from tornado.httpclient import AsyncHTTPClient

class PosmonClient(object):
    URL = 'http://drawbridge.of-sound-mind.com/~posmon/output.json'

    def __init__(self, app):
        pass

    @gen.coroutine
    def get_towers(self):
        result = {}
        resp = yield AsyncHTTPClient().fetch(self.URL)
        for line in resp.buffer:
            js = json.loads(line)
            for tower in js['towers']:
                tower['corporation'] = js['corporation']
                result[tower['location']['orbit_id']] = tower
        raise gen.Return(result)
