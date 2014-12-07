import gevent.monkey
gevent.monkey.patch_socket()
gevent.monkey.patch_ssl()

import logging
from gevent.pywsgi import WSGIServer

from . import default_config
from .app import app, db
from .calendar_service import CalendarService
from .controllers import admin, auth, setup
from .model import db as db_model

# "Use" these module objects to make flake8 quiet down
admin, auth, db_model, setup

def setup_app():
    logging.basicConfig(level=logging.DEBUG,
                        format="[%(asctime)s %(name)s %(levelname)s] %(message)s")

    # Read configs and set up the app
    app.config.from_object(default_config)
    app.config.from_envvar('POSCAL_CONFIG')

    # Start service threads
    app.cal_service = CalendarService()
    app.cal_service.start()

    # Set up database schema
    db.create_all()
    db.session.commit()

def main():
    # Serve requests
    setup_app()
    WSGIServer(('127.0.0.1', 8000), app).serve_forever()

if __name__ == '__main__':
    main()
