import json
import requests
from datetime import datetime, timedelta

from ..app import app


class Tower(object):
    _posmon_url = None

    def __init__(self, json, cache_ts, corp):
        self._json = json
        self.cache_ts = cache_ts
        self.corporation = corp

    def get_fuel_expiration(self):
        time_left = timedelta(hours=int(self._json['fuel']/self._json['fuel_per_hour']))
        return self.cache_ts + time_left

    @property
    def name(self):
        return self._json['name']

    @property
    def orbit_id(self):
        return self._json['location']['orbit_id']

    @property
    def orbit_name(self):
        return self._json['location']['orbit_name']

    @classmethod
    def fetch_all(cls):
        result = {}
        response = requests.get(app.config['POSMON_URL'])
        for line in response.iter_lines():
            if not line or not line.startswith('{'):
                continue
            obj = json.loads(line)
            corp = obj['corporation']
            start = datetime.strptime(obj['cache_ts'], '%Y-%m-%d %H:%M:%S')
            for tower_json in obj['towers']:
                tower = Tower(tower_json, start, corp)
                result[tower.orbit_id] = tower
        return result
