import json
from tornado import gen
from tornado.httpclient import AsyncHTTPClient, HTTPRequest

class GoogleCalendarAPI(object):
    BASE = 'https://www.googleapis.com/calendar/v3/'

    def __init__(self, token):
        self._token = token

    def _delete(self, ep, as_json=False):
        return self._get(ep, as_json=as_json, method='DELETE')

    @gen.coroutine
    def _get(self, ep, as_json=True, method='GET'):
        req = HTTPRequest('%s%s' % (self.BASE, ep), method=method)
        yield self._token.add_auth(req)
        resp = yield AsyncHTTPClient().fetch(req)
        if as_json:
            raise gen.Return(json.loads(resp.body))
        raise gen.Return(resp.body)

    @gen.coroutine
    def _post(self, ep, body, as_json=True, method='POST'):
        req = HTTPRequest('%s%s' % (self.BASE, ep), method=method)
        yield self._token.add_auth(req)
        req.headers['Content-Type'] = 'application/json'
        req.body = json.dumps(body)
        resp = yield AsyncHTTPClient().fetch(req)
        if as_json:
            raise gen.Return(json.loads(resp.body))
        raise gen.Return(resp.body)

    def _put(self, ep, body, as_json=True):
        return self._post(ep, body, as_json=as_json, method='PUT')

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
    def update_event(self, cal_id, event_id, summary, start, end, extra):
        body = {'kind': 'calendar#event',
                'summary': summary,
                'start': {'dateTime': start.isoformat(), 'timeZone': 'UTC'},
                'end': {'dateTime': end.isoformat(), 'timeZone': 'UTC'}}
        body.update(extra)
        raise gen.Return((yield self._put('calendars/%s/events/%s' % (cal_id, event_id), body)))

class GooglePlusAPI(GoogleCalendarAPI):
    BASE = 'https://www.googleapis.com/plus/v1/'

    @gen.coroutine
    def get_person(self, id='me'):
        result = yield self._get('people/%s' % id)
        raise gen.Return(result)
