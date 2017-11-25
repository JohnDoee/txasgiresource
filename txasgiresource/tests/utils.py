from io import BytesIO

from twisted.web.http import CACHED, NOT_MODIFIED, PRECONDITION_FAILED
from twisted.web.test.requesthelper import DummyRequest as TwistedDummyRequest


class DummyRequest(TwistedDummyRequest):
    _isSecure = False
    startedWriting = 0
    etag = None

    def __init__(self, *args, **kwargs):
        self.content = BytesIO()
        TwistedDummyRequest.__init__(self, *args, **kwargs)

    def setETag(self, etag):
        if etag:
            self.etag = etag

        tags = self.getHeader(b"if-none-match")
        if tags:
            tags = tags.split()
            if (etag in tags) or (b'*' in tags):
                self.setResponseCode(((self.method in (b"HEAD", b"GET"))
                                      and NOT_MODIFIED)
                                     or PRECONDITION_FAILED)
                return CACHED
        return None

    def write(self, data):
        if not self.startedWriting:
            self.startedWriting = 1

            if self.etag is not None:
                self.responseHeaders.setRawHeaders(b'ETag', [self.etag])

        return super(DummyRequest, self).write(data)

    def isSecure(self):
        return self._isSecure
