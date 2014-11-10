from tornado.web import url

from .controllers.admin import ForceHandler
from .controllers.auth import (
    BraveAuthStartHandler,
    BraveAuthCallbackHandler,
    LogoutHandler,
    OAuthStartHandler,
    OAuthCallbackHandler,
    )
from .controllers.setup import (
    ConfigSetPosHandler,
    HomeHandler,
    ResetHandler,
    )

ROUTES = [
    url(r'/', HomeHandler, name='home'),
    url(r'/brave/start', BraveAuthStartHandler, name='brave_start'),
    url(r'/brave/callback', BraveAuthCallbackHandler, name='brave_callback'),
    url(r'/config/set_poses', ConfigSetPosHandler),
    url(r'/logout', LogoutHandler, name='logout'),
    url(r'/oauth/start', OAuthStartHandler, name='oauth_start'),
    url(r'/oauth/callback', OAuthCallbackHandler, name='oauth_callback'),
    url(r'/reset', ResetHandler, name='reset'),
    url(r'/admin/force', ForceHandler, name='force'),
]
