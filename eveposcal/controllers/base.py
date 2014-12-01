import functools
from flask import abort, g, redirect, request, session, url_for


def auth_required(view):
    @functools.wraps(view)
    def _view(*args, **kwargs):
        if 'char_id' in session:
            g.char_id = session['char_id']
            return view(*args, **kwargs)
        else:
            return redirect(url_for('brave_start'))
    return _view


def check_referrer():
    referrer = request.referrer
    if referrer is None or not referrer.startswith(request.host_url):
        abort(403)
