import logging
import toro
from collections import defaultdict
from datetime import datetime, timedelta
from tornado import gen
from tornado.httpclient import HTTPError
from tornado.ioloop import PeriodicCallback

from .google_calendar import GoogleCalendarAPI
from .model.db import CalendarEvent, EnabledTowers, Session, Settings, Token, session_ctx
from .model.posmon import Tower

logger = logging.getLogger(__name__)

class RunAbortedException(Exception):
    def __init__(self, code):
        self.code = code

class CalendarServiceRun(object):
    def __init__(self, app, char_id):
        self.app = app
        self.cal_api = None
        self.char_id = char_id
        self.session = Session()

    @gen.coroutine
    def _get_calendar(self):
        cal_id = Settings.get(self.session, self.char_id, Settings.CALENDAR)
        try:
            yield self.cal_api.get_calendar(cal_id)
        except HTTPError as e:
            logger.debug("Failed to fetch calendar for char_id=%s", self.char_id, exc_info=True)
            if e.code == 401:
                raise RunAbortedException('auth')
            elif e.code == 404:
                raise RunAbortedException('calendar_missing')
            else:
                raise RunAbortedException('api_failure')
        raise gen.Return(cal_id)
        # XXX
        #if not cal_id:
        #    logger.debug("Making calendar for char_id=%s", self.char_id)
        #    cal_id = yield self._make_calendar(self.session, self.char_id, self.cal_api)

    @gen.coroutine
    def _get_events(self, cal_id):
        existing = {}
        for evt in CalendarEvent.get_for_char(self.session, self.char_id):
            try:
                cal_event = yield self.cal_api.get_event(cal_id, evt.event_id)
                if cal_event['status'] != 'cancelled':
                    existing[evt.orbit_id] = cal_event
            except HTTPError as e:
                logger.debug('Failed to fetch calendar event for char_id=%d orbit_id=%d',
                             self.char_id, evt.orbit_id)
                if e.code == 401:
                    raise RunAbortedException('auth')
                elif e.code != 404:
                    raise RunAbortedException('api_failure')
        raise gen.Return(existing)

    def _make_event_args(self, towers):
        args = {}
        # FIXME: Make this configurable
        offset = timedelta(days=2, hours=1)
        for orbit_id, tower in towers.iteritems():
            expires = (tower.get_fuel_expiration() - offset).replace(minute=0, second=0)
            args[orbit_id] = {
                'summary': 'Refuel %s' % (tower.name,),
                'start': expires,
                'end': expires,
                'extra': {'location': tower.orbit_name},
            }
        return args

    @gen.coroutine
    def _do_add(self, cal_id, orbit_id, event_args):
        logger.info("Creating event for char_id=%s orbit_id=%s args=%s",
                    self.char_id, orbit_id, event_args)
        try:
            response = yield self.cal_api.add_event(cal_id, **event_args)
        except HTTPError as e:
            if e.code == 401:
                raise RunAbortedException('auth')
            else:
                raise RunAbortedException('api_failure')
        event = CalendarEvent(char_id=self.char_id,
                              orbit_id=orbit_id,
                              event_id=response['id'])
        self.session.merge(event)

    @gen.coroutine
    def _do_update(self, cal_id, orbit_id, old_event, event_args):
        start = event_args['start']
        existing_start = datetime.strptime(old_event['start']['dateTime'], '%Y-%m-%dT%H:%M:%SZ')
        if abs(existing_start - start) <= timedelta(hours=1):
            return
        logger.info("Updating event for char_id=%s orbit_id=%s args=%s",
                    self.char_id, orbit_id, event_args)
        try:
            yield self.cal_api.update_event(cal_id,
                                            old_event['id'],
                                            old_event['sequence'] + 1,
                                            **event_args)
        except HTTPError as e:
            if e.code == 401:
                raise RunAbortedException('auth')
            else:
                raise RunAbortedException('api_failure')

    @gen.coroutine
    def _do_delete(self, cal_id, orbit_id, old_event):
        logger.info("Deleting event for char_id=%s orbit_id=%s",
                    self.char_id, orbit_id)
        try:
            yield self.cal_api.delete_event(cal_id, old_event['id'])
        except HTTPError as e:
            if e.code == 401:
                raise RunAbortedException('auth')
            else:
                raise RunAbortedException('api_failure')
        CalendarEvent.delete(self.session, self.char_id, orbit_id)

    @gen.coroutine
    def _run(self):
        # Set up GCal API
        token = Token.get_google_oauth(self.app, self.session, self.char_id)
        if token is None:
            raise Exception("No Google Calendar API token")
        self.cal_api = GoogleCalendarAPI(token)

        # Fetch enabled towers from posmon
        # FIXME: Do this up front / batched
        enabled = set(e.orbit_id for e in EnabledTowers.get_for_char(self.session, self.char_id))
        towers = yield Tower.fetch_all()
        for orbit_id in towers.keys():
            if orbit_id not in enabled:
                del towers[orbit_id]

        # Fetch existing calendar/events
        cal_id = yield self._get_calendar()
        existing = yield self._get_events(cal_id)

        # Compute sets to add/update/delete
        to_add = set(towers.iterkeys()) - set(existing.iterkeys())
        to_update = set(towers.iterkeys()) & set(existing.iterkeys())
        to_delete = set(existing.iterkeys()) - set(towers.iterkeys())

        # Make event arguments for all towers
        event_args = self._make_event_args(towers)

        # Perform calendar changes
        for orbit_id in to_add:
            yield self._do_add(cal_id, orbit_id, event_args[orbit_id])
        for orbit_id in to_update:
            yield self._do_update(cal_id, orbit_id, existing[orbit_id], event_args[orbit_id])
        for orbit_id in to_delete:
            yield self._do_delete(cal_id, orbit_id, existing[orbit_id])

    @gen.coroutine
    def run(self):
        commit = True
        try:
            yield self._run()
            logger.info('Run for char_id=%d successful', self.char_id)
        except RunAbortedException as e:
            logger.warn('Run for char_id=%d aborted with %s', self.char_id, e.code)
            raise
        except Exception:
            commit = False
            raise
        finally:
            if commit:
                self.session.commit()
            else:
                self.session.rollback()

class CalendarService(PeriodicCallback):
    PERIOD_MS = 60 * 60 * 1000

    def __init__(self, app):
        super(CalendarService, self).__init__(self.run_for_all, self.PERIOD_MS)
        self.app = app
        self._locks = defaultdict(toro.Lock)

    @gen.coroutine
    def make_calendar(self, char_id, token):
        cal_api = GoogleCalendarAPI(token)
        with (yield self._locks[char_id].acquire()):
            response = yield cal_api.add_calendar('EVE POS events')
            cal_id = response['id']
            with session_ctx() as session:
                Settings.set(session, char_id, Settings.CALENDAR, cal_id)
            raise gen.Return(cal_id)

    @gen.coroutine
    def run_for_all(self):
        with session_ctx() as session:
            # Get all enabled towers (to figure out what keys we need)
            enabled_towers = session.query(EnabledTowers).all()
            char_ids = list(set(e.char_id for e in enabled_towers))

            logger.info("Starting update run")
            results = [self.run_for_char(char_id) for char_id in char_ids]
            for char_id, res in zip(char_ids, results):
                try:
                    yield res
                    logger.debug("Update run succeeded for char id %s", char_id)
                except Exception:
                    logger.warn("Update run failed for char id %s", char_id, exc_info=True)
            logger.info("Update run done")

    @gen.coroutine
    def run_for_char(self, char_id):
        with (yield self._locks[char_id].acquire()):
            yield CalendarServiceRun(self.app, char_id).run()
