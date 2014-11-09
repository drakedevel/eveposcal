import urllib
from tornado import gen
from tornado.auth import GoogleOAuth2Mixin

from brave.api.tornadoclient import API

from .base import RequestHandler
from ..google_oauth import GoogleOauthToken
from ..model.db import Token

class BraveAuthStartHandler(RequestHandler):
    @gen.coroutine
    def get(self):
        nxt = self.get_argument('next', self.reverse_url('home'))
        config = self.settings['brave_auth']
        api = API(config['endpoint'],
                  config['identity'],
                  config['private'],
                  config['public'])
        result = yield api.core.authorize(
            success=self.reverse_url_full('brave_callback', status='ok',
                                          next=nxt),
            failure=self.reverse_url_full('brave_callback', status='err',
                                          next=nxt),
        )
        self.redirect(result['location'])


class BraveAuthCallbackHandler(RequestHandler):
    @gen.coroutine
    def get(self):
        if self.get_argument('status') == 'ok':
            token = self.get_argument('token')
            config = self.settings['brave_auth']
            api = API(config['endpoint'],
                      config['identity'],
                      config['private'],
                      config['public'])
            info = yield api.core.info(token)
            self.cookie['brave_token'] = token
            self.cookie['char_id'] = info['character']['id']
            self.commit_cookie()
            # FIXME: Open redirect
            if self.get_argument('next', False):
                self.redirect(urllib.unquote_plus(self.get_argument('next')))
            else:
                self.redirect(self.reverse_url('home'))
        else:
            self.finish('auth failed :(')


class LogoutHandler(RequestHandler):
    # FIXME: CSRF
    def get(self):
        self.clear_cookie()
        self.redirect(self.reverse_url('home'))


class OAuthStartHandler(RequestHandler, GoogleOAuth2Mixin):
    @gen.coroutine
    def get(self):
        nxt = self.get_argument('next', self.reverse_url('home'))
        yield self.authorize_redirect(
            redirect_uri=self.reverse_url_full('oauth_callback'),
            client_id=self.settings['google_oauth']['key'],
            scope=['https://www.googleapis.com/auth/calendar', 'email'],
            response_type='code',
            extra_params={'access_type': 'offline',
                          'approval_prompt': 'force',
                          'state': nxt})


class OAuthCallbackHandler(RequestHandler, GoogleOAuth2Mixin):
    @gen.coroutine
    def get(self):
        user = yield self.get_authenticated_user(
            redirect_uri=self.reverse_url_full('oauth_callback'),
            code=self.get_argument('code'))

        if 'char_id' in self.cookie:
            token = GoogleOauthToken.from_dict(user)
            Token.set_google_oauth(self.session, self.cookie['char_id'], token)

        # FIXME: Open redirect
        if self.get_argument('state', False):
            self.redirect(self.get_argument('state'))
        else:
            self.redirect(self.reverse_url('home'))
