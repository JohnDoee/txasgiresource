from io import BytesIO

from twisted.web.test.requesthelper import DummyRequest as TwistedDummyRequest


class DummyRequest(TwistedDummyRequest):
    _isSecure = False

    def __init__(self, *args, **kwargs):
        self.content = BytesIO()
        TwistedDummyRequest.__init__(self, *args, **kwargs)

    def isSecure(self):
        return self._isSecure
