import logging
from flask import g, render_template, redirect, request, session, url_for

from googleapiclient import discovery
from googleapiclient.errors import HttpError

from .base import auth_required, check_referrer
from ..app import app, db
from ..model.db import EnabledTowers, Settings, Token
from ..model.posmon import Tower


logger = logging.getLogger(__name__)


@app.route('/config/set_poses', methods=('POST',))
@auth_required
def config_set_poses():
    EnabledTowers.query.filter(EnabledTowers.char_id == g.char_id).delete()
    for arg, value in request.form.iteritems():
        if arg.isdigit():
            enable = EnabledTowers(char_id=g.char_id, orbit_id=int(arg))
            db.session.add(enable)
    db.session.commit()

    # Run a background update pass
    app.cal_service.run_for_char(g.char_id)

    # TODO(adrake): Flash a message
    return redirect(url_for('home'))


@app.route('/')
@auth_required
def home():
    # Check for valid Google token
    token = Token.get_google_oauth(g.char_id)
    person = None
    if token:
        api = discovery.build('plus', 'v1', credentials=token)
        person = api.people().get(userId='me').execute()

    # Check for selected POSes
    enabled = set(e.orbit_id for e in EnabledTowers.get_for_char(g.char_id))
    towers = Tower.fetch_all().values()
    towers.sort(key=lambda t: t.orbit_name)

    db.session.commit()

    return render_template('home.html',
                           char_name=session['char_name'],
                           enabled=enabled,
                           person=person,
                           towers=towers)


@app.route('/reset')
@auth_required
def reset():
    check_referrer()

    # Get the user's Google API token
    token = Token.get_google_oauth(g.char_id)
    if token is None:
        return "This only works after you've linked your Google Calendar API token"
    cal_api = discovery.build('calendar', 'v3', credentials=token)

    # Delete calendar linked to account
    cal_id = Settings.get(g.char_id, Settings.CALENDAR)
    if cal_id:
        try:
            cal_api.calendars().delete(calendarId=cal_id).execute()
        except HttpError:
            logger.debug("Failed to delete calendar", exc_info=True)

    # Create a new calendar
    app.cal_service.make_calendar(g.char_id, token)
    db.session.commit()

    # Run synchronous update pass
    app.cal_service.run_for_char(g.char_id).join()

    return redirect(url_for('home'))
