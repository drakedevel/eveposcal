import json
import logging
import os
import sys
from binascii import unhexlify
from ecdsa.keys import SigningKey, VerifyingKey
from ecdsa.curves import NIST256p
from hashlib import sha256
from sqlalchemy import create_engine
from tornado import web
from tornado.ioloop import IOLoop

from .calendar_service import CalendarService
from .model.db import Base, Session
from .model.posmon import Tower
from .routing import ROUTES

def main():
    logging.basicConfig(level=logging.DEBUG,
                        format="[%(asctime)s %(name)s %(levelname)s] %(message)s")

    # Read config
    with open(sys.argv[1]) as config_f:
        config = json.load(config_f)

    # Convert config keys to actual keys
    config['brave_auth']['public'] = VerifyingKey.from_string(
        unhexlify(config['brave_auth']['public']), curve=NIST256p, hashfunc=sha256)
    config['brave_auth']['private'] = SigningKey.from_string(
        unhexlify(config['brave_auth']['private']), curve=NIST256p, hashfunc=sha256)

    # Configure web routes
    app = web.Application(ROUTES, debug=config['debug'])
    app.settings.update(config)
    app.settings['template_path'] = os.path.join(os.path.dirname(__file__), '..', 'templates')
    app.settings['xsrf_cookies'] = True
    app.listen(8000, address='127.0.0.1', xheaders=True)

    # Configure database engine
    engine = create_engine(app.settings['database'], pool_recycle=3600)
    Session.configure(bind=engine)
    Base.metadata.create_all(engine)
    Tower.configure(app.settings['posmon_url'])

    # Start service coroutines
    app.cal_service = CalendarService(app)
    app.cal_service.start()

    # Start IO loop
    IOLoop.instance().start()

if __name__ == '__main__':
    main()
