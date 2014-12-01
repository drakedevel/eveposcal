import gevent
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from gevent.lock import Semaphore

from googleapiclient import discovery
from googleapiclient.errors import HttpError

from .app import app, db
from .model.db import CalendarEvent, EnabledTowers, Settings, Token
from .model.posmon import Tower

logger = logging.getLogger(__name__)


class RunAbortedException(Exception):
    def __init__(self, code):
        self.code = code


class CalendarServiceRun(object):
    def __init__(self, char_id):
        self.cal_api = None
        self.char_id = char_id

    @staticmethod
    def _format_date(dt):
        return {'dateTime': dt.isoformat() + 'Z', 'timeZone': 'UTC'}

    @staticmethod
    def _parse_date(dt):
        return datetime.strptime(dt['dateTime'], '%Y-%m-%dT%H:%M:%SZ')

    def _get_calendar(self):
        cal_id = Settings.get(self.char_id, Settings.CALENDAR)
        try:
            self.cal_api.calendars().get(calendarId=cal_id).execute()
        except HttpError as e:
            logger.debug("Failed to fetch calendar for char_id=%s", self.char_id, exc_info=True)
            if e.resp.status == 401:
                raise RunAbortedException('auth')
            elif e.resp.status == 404:
                raise RunAbortedException('calendar_missing')
            else:
                raise RunAbortedException('api_failure')
        return cal_id

    def _get_events(self, cal_id):
        existing = {}
        for evt in CalendarEvent.get_for_char(self.char_id):
            try:
                cal_event = self.cal_api.events().get(calendarId=cal_id,
                                                      eventId=evt.event_id).execute()
                if cal_event['status'] != 'cancelled':
                    existing[evt.orbit_id] = cal_event
            except HttpError as e:
                logger.debug('Failed to fetch calendar event for char_id=%d orbit_id=%d',
                             self.char_id, evt.orbit_id)
                if e.resp.status == 401:
                    raise RunAbortedException('auth')
                elif e.resp.status != 404:
                    raise RunAbortedException('api_failure')
        return existing

    def _make_event_args(self, towers):
        args = {}
        # FIXME: Make this configurable
        offset = timedelta(days=2, hours=1)
        for orbit_id, tower in towers.iteritems():
            expires = (tower.get_fuel_expiration() - offset).replace(minute=0, second=0)
            args[orbit_id] = {
                'summary': 'Refuel %s' % (tower.name,),
                'start': self._format_date(expires),
                'end': self._format_date(expires),
                'location': tower.orbit_name,
            }
        return args

    def _do_add(self, cal_id, orbit_id, event_args):
        logger.info("Creating event for char_id=%s orbit_id=%s args=%s",
                    self.char_id, orbit_id, event_args)
        try:
            response = self.cal_api.events().insert(calendarId=cal_id,
                                                    body=event_args).execute()
        except HttpError as e:
            if e.resp.status == 401:
                raise RunAbortedException('auth')
            else:
                raise RunAbortedException('api_failure')
        event = CalendarEvent(char_id=self.char_id,
                              orbit_id=orbit_id,
                              event_id=response['id'])
        db.session.merge(event)

    def _do_update(self, cal_id, orbit_id, old_event, event_args):
        start = self._parse_date(event_args['start'])
        existing_start = self._parse_date(old_event['start'])
        if abs(existing_start - start) <= timedelta(hours=1):
            return
        logger.info("Updating event for char_id=%s orbit_id=%s args=%s",
                    self.char_id, orbit_id, event_args)
        try:
            body = {'sequence': old_event['sequence'] + 1}
            body.update(event_args)
            self.cal_api.events().update(calendarId=cal_id,
                                         eventId=old_event['id'],
                                         body=body).execute()
        except HttpError as e:
            if e.resp.status == 401:
                raise RunAbortedException('auth')
            else:
                raise RunAbortedException('api_failure')

    def _do_delete(self, cal_id, orbit_id, old_event):
        logger.info("Deleting event for char_id=%s orbit_id=%s",
                    self.char_id, orbit_id)
        try:
            self.cal_api.events().delete(calendarId=cal_id, eventId=old_event['id']).execute()
        except HttpError as e:
            if e.resp.status == 401:
                raise RunAbortedException('auth')
            else:
                raise RunAbortedException('api_failure')
        CalendarEvent.delete(self.char_id, orbit_id)

    def _run(self):
        # Set up GCal API
        token = Token.get_google_oauth(self.char_id)
        if token is None:
            raise Exception("No Google Calendar API token")
        self.cal_api = discovery.build('calendar', 'v3', credentials=token)

        # Fetch enabled towers from posmon
        # FIXME: Do this up front / batched
        enabled = set(e.orbit_id for e in EnabledTowers.get_for_char(self.char_id))
        towers = Tower.fetch_all()
        for orbit_id in towers.keys():
            if orbit_id not in enabled:
                del towers[orbit_id]

        # Fetch existing calendar/events
        cal_id = self._get_calendar()
        existing = self._get_events(cal_id)

        # Compute sets to add/update/delete
        to_add = set(towers.iterkeys()) - set(existing.iterkeys())
        to_update = set(towers.iterkeys()) & set(existing.iterkeys())
        to_delete = set(existing.iterkeys()) - set(towers.iterkeys())

        # Make event arguments for all towers
        event_args = self._make_event_args(towers)

        # Perform calendar changes
        for orbit_id in to_add:
            self._do_add(cal_id, orbit_id, event_args[orbit_id])
        for orbit_id in to_update:
            self._do_update(cal_id, orbit_id, existing[orbit_id], event_args[orbit_id])
        for orbit_id in to_delete:
            self._do_delete(cal_id, orbit_id, existing[orbit_id])

    def run(self):
        commit = True
        try:
            self._run()
            logger.info('Run for char_id=%d successful', self.char_id)
        except RunAbortedException as e:
            logger.warn('Run for char_id=%d aborted with %s', self.char_id, e.code)
            raise
        except Exception:
            commit = False
            raise
        finally:
            if commit:
                db.session.commit()


class CalendarService(object):
    PERIOD_MS = 60 * 60 * 1000

    def __init__(self):
        self._greenlet = None
        self._locks = defaultdict(Semaphore)

    def _greenlet_main(self):
        next_t = time.time() + self.PERIOD_MS
        while True:
            if time.time() < next_t:
                gevent.sleep(next_t - time.time())
                continue
            else:
                next_t = time.time() + self.PERIOD_MS

            self.run_for_all()

    def make_calendar(self, char_id, token):
        cal_api = discovery.build('calendar', 'v3', credentials=token)
        response = cal_api.calendars().insert(body={'summary': 'EVE POS events'}).execute()
        cal_id = response['id']
        Settings.set(char_id, Settings.CALENDAR, cal_id)
        return cal_id

    def run_for_all(self):
        with app.app_context():
            # Get all enabled towers (to figure out what keys we need)
            enabled_towers = EnabledTowers.query.all()
            char_ids = list(set(e.char_id for e in enabled_towers))

            logger.info("Starting update run")
            greenlets = [self.run_for_char(char_id) for char_id in char_ids]
            for char_id, greenlet in zip(char_ids, greenlets):
                greenlet.join()
                if greenlet.successful():
                    logger.debug("Update run succeeded for char id %s", char_id)
                else:
                    logger.warn("Update run failed for char id %s: %s", char_id,
                                greenlet.exception)
            logger.info("Update run done")

    def run_for_char(self, char_id):
        def _run():
            with self._locks[char_id]:
                CalendarServiceRun(char_id).run()
        with app.app_context():
            return gevent.spawn(_run)

    def start(self):
        if self._greenlet:
            return
        self._greenlet = gevent.spawn(self._greenlet_main)

    def stop(self):
        if self._greenlet:
            self._greenlet.kill()
            self._greenlet = None
