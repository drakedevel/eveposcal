import json
import logging
from tornado import gen
from tornado.httpclient import AsyncHTTPClient, HTTPError, HTTPRequest

logger = logging.getLogger(__name__)

class GoogleCalendarAPI(object):
    BASE = 'https://www.googleapis.com/calendar/v3/'
    TRIES = 2

    def __init__(self, token):
        self._token = token

    @gen.coroutine
    def _do_request(self, method, ep, body=None, as_json=False):
        url = '%s%s' % (self.BASE, ep)
        for try_i in range(self.TRIES):
            try:
                req = HTTPRequest(url, method=method)
                yield self._token.add_auth(req)
                if body is not None:
                    req.headers['Content-Type'] = 'application/json'
                    req.body = json.dumps(body)
                resp = yield AsyncHTTPClient().fetch(req)
                logger.debug('%s %s (attempt %d) => %d', method, ep, try_i, resp.code)
                if as_json:
                    raise gen.Return(json.loads(resp.body))
                raise gen.Return(resp.body)
            except HTTPError as e:
                logger.debug('%s %s => %d', method, ep, e.code)
                if try_i < (self.TRIES - 1) and e.code == 401:
                    yield self._token.renew()
                else:
                    raise

    def _delete(self, ep, as_json=False):
        return self._do_request('DELETE', ep, as_json=as_json)

    def _get(self, ep, as_json=True):
        return self._do_request('GET', ep, as_json=as_json)

    def _post(self, ep, body, as_json=True):
        return self._do_request('POST', ep, body=body, as_json=as_json)

    def _put(self, ep, body, as_json=True):
        return self._do_request('PUT', ep, body=body, as_json=as_json)

    @gen.coroutine
    def add_calendar(self, summary):
        body = {'kind': 'calendar#calendar', 'summary': summary}
        raise gen.Return((yield self._post('calendars', body)))

    @gen.coroutine
    def add_event(self, cal_id, summary, start, end, extra):
        body = {'kind': 'calendar#event',
                'summary': summary,
                'start': {'dateTime': start.isoformat(), 'timeZone': 'UTC'},
                'end': {'dateTime': end.isoformat(), 'timeZone': 'UTC'}}
        body.update(extra)
        raise gen.Return((yield self._post('calendars/%s/events' % cal_id, body)))

    @gen.coroutine
    def delete_calendar(self, cal_id):
        raise gen.Return((yield self._delete('calendars/%s' % cal_id)))

    @gen.coroutine
    def delete_event(self, cal_id, event_id):
        raise gen.Return((yield self._delete('calendars/%s/events/%s' % (cal_id, event_id))))

    @gen.coroutine
    def get_calendar(self, id):
        raise gen.Return((yield self._get('calendars/%s' % id)))

    @gen.coroutine
    def get_event(self, cal_id, event_id):
        raise gen.Return((yield self._get('calendars/%s/events/%s' % (cal_id, event_id))))

    @gen.coroutine
    def update_event(self, cal_id, event_id, sequence, summary, start, end, extra):
        body = {'kind': 'calendar#event',
                'summary': summary,
                'start': {'dateTime': start.isoformat(), 'timeZone': 'UTC'},
                'end': {'dateTime': end.isoformat(), 'timeZone': 'UTC'},
                'sequence': sequence}
        body.update(extra)
        raise gen.Return((yield self._put('calendars/%s/events/%s' % (cal_id, event_id), body)))

class GooglePlusAPI(GoogleCalendarAPI):
    BASE = 'https://www.googleapis.com/plus/v1/'

    @gen.coroutine
    def get_person(self, id='me'):
        result = yield self._get('people/%s' % id)
        raise gen.Return(result)
