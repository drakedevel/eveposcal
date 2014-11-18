from tornado import gen

from .base import RequestHandler

class ForceHandler(RequestHandler):
    @gen.coroutine
    def get(self):
        yield self.application.cal_service._do_update()
        self.finish('OK')
        
