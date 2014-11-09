import json
from sqlalchemy import Column, Integer, String, VARBINARY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from ..google_oauth import GoogleOauthToken

Base = declarative_base()

Session = sessionmaker()

class CalendarEvent(Base):
    __tablename__ = 'calendar_event'

    char_id = Column(Integer, primary_key=True)
    orbit_id = Column(Integer, primary_key=True)
    event_id = Column(String(256))

    @classmethod
    def get_for_char(cls, session, char_id):
        return session.query(cls).filter_by(char_id=char_id).all()

class EnabledTowers(Base):
    __tablename__ = 'enabled_tower'

    char_id = Column(Integer, primary_key=True)
    orbit_id = Column(Integer, primary_key=True)


class Settings(Base):
    __tablename__ = 'settings'

    CALENDAR = 0

    char_id = Column(Integer, primary_key=True)
    key = Column(Integer, primary_key=True)
    value = Column(String(256))

    @classmethod
    def get(cls, session, char_id, key):
        return cls.multiget(session, [char_id], key).get(char_id)

    @classmethod
    def multiget(cls, session, char_ids, key):
        objs = session.query(cls).filter(cls.key == key, cls.char_id.in_(char_ids)).all()
        return {obj.char_id: obj.value for obj in objs}

    @classmethod
    def set(cls, session, char_id, key, value):
        obj = cls(char_id=char_id, key=key, value=value)
        session.merge(obj)


class Token(Base):
    __tablename__ = 'token'

    GOOGLE_OAUTH = 0

    char_id = Column(Integer, primary_key=True)
    kind = Column(String(10), primary_key=True)
    value = Column(VARBINARY(256))

    @classmethod
    def clear_google_oauth(cls, session, char_id):
        session.query(cls).filter(cls.char_id == char_id).filter(cls.kind == cls.GOOGLE_OAUTH).delete()

    @classmethod
    def get_google_oauth(cls, app, session, char_id):
        return cls.multiget_google_oauth(app, session, [char_id]).get(char_id)

    @classmethod
    def multiget_google_oauth(cls, app, session, char_ids):
        objs = session.query(cls).filter(cls.kind == cls.GOOGLE_OAUTH,
                                         cls.char_id.in_(char_ids)).all()
        return {obj.char_id: GoogleOauthToken.from_orm(obj, app) for obj in objs}

    @classmethod
    def set_google_oauth(cls, session, char_id, token):
        obj = Token(char_id=char_id, kind=Token.GOOGLE_OAUTH, value=json.dumps(token.to_dict()))
        session.merge(obj)
