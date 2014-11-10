import logging
import toro
from datetime import datetime, timedelta
from tornado import gen
from tornado.httpclient import HTTPError
from tornado.ioloop import PeriodicCallback

from .google_calendar import GoogleCalendarAPI
from .model.db import CalendarEvent, EnabledTowers, Session, Settings, Token
from .model.posmon import Tower

logger = logging.getLogger(__name__)

class CalendarService(PeriodicCallback):
    PERIOD_MS = 60 * 60 * 1000

    def __init__(self, app):
        super(CalendarService, self).__init__(self._run, self.PERIOD_MS)
        self.app = app
        self._locks = {}

    @gen.coroutine
    def _make_calendar(self, session, char_id, cal_api):
        response = yield cal_api.add_calendar('EVE POS events')
        cal_id = response['id']
        Settings.set(session, char_id, Settings.CALENDAR, cal_id)
        session.commit()
        raise gen.Return(cal_id)

    @gen.coroutine
    def _run_for_char(self, char_id):
        if char_id not in self._locks:
            self._locks[char_id] = toro.Lock()
        with (yield self._locks[char_id].acquire()):
            session = Session()
            commit = True
            try:
                yield self._run_for_char_inner(session, char_id)
            except Exception:
                session.rollback()
                commit = False
            finally:
                if commit:
                    session.commit()

    @gen.coroutine
    def _run_for_char_inner(self, session, char_id):
        token = Token.get_google_oauth(self.app, session, char_id)
        if token is None:
            raise Exception("No Google Calendar API token")
        cal_api = GoogleCalendarAPI(token)

        # Validate the saved calendar API, and (re)create if necessary
        cal_id = Settings.get(session, char_id, Settings.CALENDAR)
        try:
            yield cal_api.get_calendar(cal_id)
        except HTTPError:
            logging.debug("Failed to fetch calendar for char_id=%s", char_id, exc_info=True)
            cal_id = None
        if not cal_id:
            logging.debug("Making calendar for char_id=%s", char_id)
            cal_id = yield self._make_calendar(session, char_id, cal_api)

        # Fetch enabled towers
        # FIXME: Do this earlier en-masse
        enabled = set(e.orbit_id for e in
                      session.query(EnabledTowers).filter(EnabledTowers.char_id == char_id).all())

        # Fetch all towers from posmon
        # FIXME: Do this earlier en-masse
        towers = yield Tower.fetch_all()
        for orbit_id in towers.keys():
            if orbit_id not in enabled:
                del towers[orbit_id]

        # Fetch all exiting events from database (validating against cal API)
        # FIXME: Batch this
        existing = {}
        for evt in CalendarEvent.get_for_char(session, char_id):
            try:
                cal_event = yield cal_api.get_event(cal_id, evt.event_id)
                if cal_event['status'] != 'cancelled':
                    existing[evt.orbit_id] = cal_event
                logger.debug('char_id=%d orbit_id=%d existing=%s',
                             char_id, evt.orbit_id, cal_event)
            except HTTPError:
                pass

        # Compute sets to add/update/delete
        to_add = set(towers.iterkeys()) - set(existing.iterkeys())
        to_update = set(towers.iterkeys()) & set(existing.iterkeys())
        to_delete = set(existing.iterkeys()) - set(towers.iterkeys())

        # FIXME: Make this configurable
        offset = timedelta(days=2, hours=1)

        # Perform adds
        for orbit_id in to_add:
            tower = towers[orbit_id]
            expires = (tower.get_fuel_expiration() - offset).replace(minute=0, second=0)
            logger.info("Creating event for char_id=%s orbit_id=%s expires=%s",
                        char_id, tower.orbit_id, expires)
            response = yield cal_api.add_event(cal_id,
                                               summary='Refuel %s' % (tower.name,),
                                               start=expires,
                                               end=expires,
                                               extra={'location': tower.orbit_name})
            event = CalendarEvent(char_id=char_id,
                                  orbit_id=orbit_id,
                                  event_id=response['id'])
            session.merge(event)

        # Perform updates
        # FIXME: Merge this with adds
        for orbit_id in to_update:
            tower = towers[orbit_id]
            expires = (tower.get_fuel_expiration() - offset).replace(minute=0, second=0)
            event = existing[orbit_id]
            existing_expires = datetime.strptime(event['start']['dateTime'], '%Y-%m-%dT%H:%M:%SZ')
            if abs(existing_expires - expires) <= timedelta(hours=1):
                continue
            logger.info("Updating event for char_id=%s orbit_id=%s expires=%s",
                        char_id, tower.orbit_id, expires)
            yield cal_api.update_event(cal_id,
                                       event['id'],
                                       summary='Refuel %s' % (tower.name,),
                                       start=expires,
                                       end=expires,
                                       extra={'location': tower.orbit_name,
                                              'sequence': event['sequence'] + 1})

        # Perform deletes
        for orbit_id in to_delete:
            event = existing[orbit_id]
            logger.info("Deleting event for char_id=%s orbit_id=%s",
                        char_id, tower.orbit_id)
            try:
                yield cal_api.delete_event(cal_id, event['id'])
            except HTTPError:
                pass
            session.query(CalendarEvent).filter_by(char_id=char_id, orbit_id=orbit_id).delete()

    @gen.coroutine
    def _run(self):
        session = Session()
        commit = True
        try:
            # Get all enabled towers (to figure out what keys we need)
            enabled_towers = session.query(EnabledTowers).all()
            char_ids = list(set(e.char_id for e in enabled_towers))

            logger.info("Starting update run")
            results = [self._run_for_char(char_id) for char_id in char_ids]
            for char_id, res in zip(char_ids, results):
                try:
                    yield res
                    logger.debug("Update run succeeded for char id %s", char_id)
                except Exception:
                    logger.warn("Update run failed for char id %s", char_id, exc_info=True)
            logger.info("Update run done")
        except Exception:
            session.rollback()
            commit = False
        finally:
            if commit:
                session.commit()
