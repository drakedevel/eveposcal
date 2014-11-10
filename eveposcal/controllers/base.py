import json
import urllib
from tornado import web

from ..model.db import Session

class RequestHandler(web.RequestHandler):
    COOKIE_JAR = 'jar'

    def check_referer(self):
        referer = self.request.headers.get('Referer', None)
        if referer is None:
            raise web.HTTPError(403)
        prefix = '%s://%s/' % (self.request.protocol, self.request.host)
        if not referer.startswith(prefix):
            raise web.HTTPError(403)

    def clear_cookie(self):
        super(RequestHandler, self).clear_cookie(self.COOKIE_JAR)

    def commit_cookie(self):
        # TODO: expires
        self.set_secure_cookie(self.COOKIE_JAR, json.dumps(self.cookie))

    def get_current_user(self):
        return self.cookie.get('char_id')

    def get_login_url(self):
        return self.reverse_url('brave_start')

    def on_finish(self):
        super(RequestHandler, self).on_finish()
        if 200 <= self.get_status() < 500:
            self.session.commit()
        else:
            self.session.rollback()

    def prepare(self):
        super(RequestHandler, self).prepare()
        # TODO: max_age
        cookie = self.get_secure_cookie(self.COOKIE_JAR)
        self.cookie = json.loads(cookie) if cookie else {}
        self.session = Session()

    def reverse_url(self, name, *args, **kwargs):
        path = super(RequestHandler, self).reverse_url(name, *args)
        if kwargs:
            path += '?' + urllib.urlencode(kwargs)
        return path

    def reverse_url_full(self, name, *args, **kwargs):
        path = self.reverse_url(name, *args, **kwargs)
        return '%s://%s%s' % (self.request.protocol,
                              self.request.host,
                              path)
