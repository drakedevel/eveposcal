from contextlib import contextmanager

from oauth2client.client import OAuth2Credentials, Storage

from ..app import db


class CalendarEvent(db.Model):
    __tablename__ = 'calendar_event'

    char_id = db.Column(db.Integer, primary_key=True)
    orbit_id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(256))

    @classmethod
    def delete(cls, char_id, orbit_id):
        cls.query.filter_by(char_id=char_id, orbit_id=orbit_id).delete()

    @classmethod
    def get_for_char(cls, char_id):
        return cls.query.filter_by(char_id=char_id).all()


class EnabledTowers(db.Model):
    __tablename__ = 'enabled_tower'

    char_id = db.Column(db.Integer, primary_key=True)
    orbit_id = db.Column(db.Integer, primary_key=True)

    @classmethod
    def get_for_char(cls, char_id):
        return cls.query.filter_by(char_id=char_id).all()


class Settings(db.Model):
    __tablename__ = 'settings'

    CALENDAR = 0

    char_id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.String(256))

    @classmethod
    def get(cls, char_id, key):
        return cls.multiget([char_id], key).get(char_id)

    @classmethod
    def multiget(cls, char_ids, key):
        objs = cls.query.filter(cls.key == key, cls.char_id.in_(char_ids)).all()
        return {obj.char_id: obj.value for obj in objs}

    @classmethod
    def set(cls, char_id, key, value):
        obj = cls(char_id=char_id, key=key, value=value)
        db.session.merge(obj)


class Token(db.Model):
    __tablename__ = 'token'

    GOOGLE_OAUTH = 0

    char_id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(10), primary_key=True)
    value = db.Column(db.VARBINARY(4096))

    class _Storage(Storage):
        def __init__(self, t):
            self._t = t

        def locked_get(self):
            db.session.refresh(self._t)
            creds = OAuth2Credentials.from_json(self._t.value)
            creds.set_store(self)
            return creds

        def locked_put(self, creds):
            self._t.value = creds.to_json()
            db.session.merge(self._t)

        def locked_delete(self):
            db.session.delete(self._t)

    @classmethod
    def clear_google_oauth(cls, char_id):
        cls.query.filter(cls.char_id == char_id).filter(cls.kind == cls.GOOGLE_OAUTH).delete()

    @classmethod
    def get_google_oauth(cls, char_id):
        return cls.multiget_google_oauth([char_id]).get(char_id)

    @classmethod
    def multiget_google_oauth(cls, char_ids):
        objs = cls.query.filter(cls.kind == cls.GOOGLE_OAUTH,
                                cls.char_id.in_(char_ids)).all()
        result = {}
        for obj in objs:
            creds = OAuth2Credentials.from_json(obj.value)
            creds.set_store(cls._Storage(obj))
            result[obj.char_id] = creds
        return result

    @classmethod
    def set_google_oauth(cls, char_id, creds):
        obj = Token(char_id=char_id, kind=Token.GOOGLE_OAUTH, value=creds.to_json())
        db.session.merge(obj)


@contextmanager
def session_ctx():
    #session = Session()
    try:
        yield None
    except Exception:
        pass
        #session.rollback()
    else:
        pass
        #session.commit()
