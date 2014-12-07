from .base import auth_required
from ..app import app


@app.route('/admin/force')
@auth_required
def get():
    app.cal_service.run_for_all()
    return 'OK'
