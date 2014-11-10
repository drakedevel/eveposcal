import logging
from tornado import gen, web
from tornado.httpclient import HTTPError

from .base import RequestHandler
from ..google_calendar import GoogleCalendarAPI, GooglePlusAPI
from ..model.db import EnabledTowers, Settings, Token
from ..posmon_model import PosmonClient


logger = logging.getLogger(__name__)


class ConfigSetPosHandler(RequestHandler):
    @gen.coroutine
    @web.authenticated
    def post(self):
        self.session.query(EnabledTowers).filter(EnabledTowers.char_id == self.current_user).delete()
        for arg, value in self.request.body_arguments.iteritems():
            if arg.isdigit():
                self.session.add(EnabledTowers(char_id=self.current_user, orbit_id=int(arg)))
        self.application.cal_service._run_for_char(self.current_user)
        self.redirect(self.reverse_url('home'))


class HomeHandler(RequestHandler):
    @gen.coroutine
    @web.authenticated
    def get(self):
        # Check for valid Google token
        token = Token.get_google_oauth(self.application,
                                       self.session,
                                       self.current_user)
        person = None
        if token:
            api = GooglePlusAPI(token)
            try:
                person = yield api.get_person()
            except HTTPError:
                Token.clear_google_oauth(self.session, self.current_user)

        # Check for selected POSes
        enabled = set(e.orbit_id for e in
                      self.session.query(EnabledTowers)
                          .filter(EnabledTowers.char_id == self.current_user).all())

        towers = yield PosmonClient(self.application).get_towers()

        self.render('home.html',
                    enabled=enabled,
                    person=person,
                    towers=towers)


class ResetHandler(RequestHandler):
    @gen.coroutine
    @web.authenticated
    def get(self):
        self.check_referer()

        # Get the user's Google API token
        token = Token.get_google_oauth(self.application, self.session, self.current_user)
        if token is None:
            self.finish("This only works after you've linked your Google Calendar API token")
        cal_api = GoogleCalendarAPI(token)

        # Delete calendar linked to account
        cal_id = Settings.get(self.session, self.current_user, Settings.CALENDAR)
        if cal_id:
            try:
                yield cal_api.delete_calendar(cal_id)
            except HTTPError:
                logger.debug("Failed to delete calendar", exc_info=True)

        # Run synchronous update pass
        yield self.application.cal_service._run_for_char(self.current_user)

        self.redirect(self.reverse_url('home'))
