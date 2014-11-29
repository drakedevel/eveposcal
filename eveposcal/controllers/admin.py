from tornado import gen

from .base import RequestHandler

class ForceHandler(RequestHandler):
    @gen.coroutine
    def get(self):
        yield self.application.cal_service.run_for_all()
        self.finish('OK')
