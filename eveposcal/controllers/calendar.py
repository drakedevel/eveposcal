import logging
from tornado import gen
from tornado.httpclient import HTTPError

from .base import RequestHandler
from ..google_calendar import GoogleCalendarAPI
from ..model.db import CalendarEvent, Settings, Token
from ..model.posmon import Tower


logger = logging.getLogger(__name__)


class POSStatusHandler(RequestHandler):
    @gen.coroutine
    def get(self):
        self.set_header('Content-Type', 'text/plain')
        towers = yield Tower.fetch_all()
        for orbit_id, tower in towers.iteritems():
            self.write('    %32s %24s: %s\n' % (tower.name,
                                                tower.orbit_name,
                                                tower.get_fuel_expiration()))


class CreateCalendar(RequestHandler):
    @gen.coroutine
    def get(self):
        self.set_header('Content-Type', 'text/plain')
        token = Token.get_google_oauth(self.application,
                                       self.session,
                                       self.current_user)
        api = GoogleCalendarAPI(token)
        cal_id = Settings.get(self.session, self.current_user, Settings.CALENDAR)
        if cal_id:
            try:
                yield api.get_calendar(cal_id)
            except HTTPError:
                cal_id = None
        if not cal_id:
            response = yield api.add_calendar('EVE POS events')
            cal_id = response['id']
            Settings.set(self.session, self.current_user, Settings.CALENDAR, cal_id)

        self.finish(cal_id)


class NukeEvents(RequestHandler):
    @gen.coroutine
    def get(self):
        token = Token.get_google_oauth(self.application, self.session, self.current_user)
        api = GoogleCalendarAPI(token)
        cal_id = Settings.get(self.session, self.current_user, Settings.CALENDAR)
        for evt in CalendarEvent.get_for_char(self.session, self.current_user):
            try:
                yield api.delete_event(cal_id, evt.event_id)
            except HTTPError:
                pass
            self.session.delete(evt)
