import json
import urllib
from datetime import datetime, timedelta
from tornado import gen
from tornado.httpclient import AsyncHTTPClient, HTTPRequest

class GoogleOauthToken(object):
    DATE_FORMAT = '%Y-%m-%dT%H:%M:%S'

    def __init__(self, access_token, expires, refresh_token=None):
        self._access_token = access_token
        self._app = None
        self._orm = None
        self.expires = expires
        self.refresh_token = refresh_token

    @classmethod
    def from_dict(cls, dct):
        if 'expires_in' in dct:
            expires = datetime.now() + timedelta(seconds=dct['expires_in'])
        else:
            expires = datetime.strptime(dct['expires'], cls.DATE_FORMAT)
        return cls(dct['access_token'],
                   expires,
                   dct.get('refresh_token'))

    @classmethod
    def from_orm(cls, orm, app):
        result = cls.from_dict(json.loads(orm.value))
        result._app = app
        result._orm = orm
        return result

    @gen.coroutine
    def add_auth(self, req):
        token = yield self.get_access_token()
        req.headers['Authorization'] = 'Bearer %s' % token

    @gen.coroutine
    def get_access_token(self):
        if datetime.now() > self.expires:
            yield self.renew()
        raise gen.Return(self._access_token)

    @gen.coroutine
    def renew(self):
        if not self.refresh_token:
            raise Exception("Token expired and can't be renewed!")
        req = HTTPRequest('https://accounts.google.com/o/oauth2/token', method='POST')
        req.body = urllib.urlencode({'refresh_token': self.refresh_token,
                                     'client_id': self._app.settings['google_oauth']['key'],
                                     'client_secret': self._app.settings['google_oauth']['secret'],
                                     'grant_type': 'refresh_token'})
        result = yield AsyncHTTPClient().fetch(req)
        new_token = GoogleOauthToken.from_dict(json.loads(result.body))
        self._access_token = new_token._access_token
        self.expires = new_token.expires
        if self._orm:
            self._orm.value = json.dumps(self.to_dict())

    def to_dict(self):
        return {'access_token': self._access_token,
                'expires': self.expires.strftime(self.DATE_FORMAT),
                'refresh_token': self.refresh_token}
