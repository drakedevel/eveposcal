import urllib
from binascii import unhexlify
from ecdsa.curves import NIST256p
from ecdsa.keys import SigningKey, VerifyingKey
from flask import g, redirect, request, session, url_for
from hashlib import sha256

from brave.api.client import API
from oauth2client.client import OAuth2WebServerFlow

from .base import check_referrer, auth_required
from ..app import app, db
from ..model.db import Settings, Token


def _get_brave_api():
    config = app.config['BRAVE_AUTH']
    return API(config['endpoint'],
               config['identity'],
               SigningKey.from_string(unhexlify(config['private']),
                                      curve=NIST256p, hashfunc=sha256),
               VerifyingKey.from_string(unhexlify(config['public']),
                                        curve=NIST256p, hashfunc=sha256))


@app.route('/brave/start')
def brave_start():
    nxt = request.args.get('next', url_for('home'))
    result = _get_brave_api().core.authorize(
        success=url_for('brave_callback', status='ok', next=nxt, _external=True),
        failure=url_for('brave_callback', status='err', next=nxt, _external=True),
    )
    return redirect(result.location)


@app.route('/brave/callback')
def brave_callback():
    if request.args['status'] == 'ok':
        token = request.args['token']
        info = _get_brave_api().core.info(token)
        session['brave_token'] = token
        session['char_id'] = info.character.id
        session['char_name'] = info.character.name
        # FIXME: Open redirect
        if 'next' in request.args:
            return redirect(urllib.unquote_plus(request.args['next']))
        else:
            return redirect(url_for('home'))
    else:
        return 'auth failed :('


@app.route('/logout')
def logout():
    check_referrer()
    if 'brave_token' in session:
        _get_brave_api().core.deauthorize(session['brave_token'])
    session.clear()
    return redirect(url_for('home'))


def _get_oauth_flow(nxt):
    return OAuth2WebServerFlow(
        client_id=app.config['GOOGLE_OAUTH']['key'],
        client_secret=app.config['GOOGLE_OAUTH']['secret'],
        scope=['https://www.googleapis.com/auth/calendar', 'email'],
        redirect_uri=url_for('oauth_callback', _external=True),
        approval_prompt='force',
        state=nxt)


@app.route('/oauth/start')
@auth_required
def oauth_start():
    nxt = request.args.get('next', url_for('home'))
    return redirect(_get_oauth_flow(nxt).step1_get_authorize_url())


@app.route('/oauth/callback')
@auth_required
def oauth_callback():
    nxt = request.args['state']

    # Fetch and save OAuth credentials
    creds = _get_oauth_flow(nxt).step2_exchange(request.args['code'])
    Token.set_google_oauth(g.char_id, creds)
    db.session.commit()

    # Kick off a background update if the calendar needs to be created
    if not Settings.get(g.char_id, Settings.CALENDAR):
        app.cal_service.make_calendar(g.char_id, creds)
        db.session.commit()
        app.cal_service.run_for_char(g.char_id)

    # FIXME: Open redirect
    return redirect(nxt)
