import logging

from autobahn.twisted.resource import WebSocketResource
from twisted.web import resource, server

from .application import ApplicationManager
from .http import ASGIHTTPResource
from .ws import ASGIWebSocketServerFactory

logger = logging.getLogger(__name__)


class ASGIResource(resource.Resource):
    isLeaf = True

    def __init__(self,
                 application,
                 root_path='',
                 http_timeout=120,
                 websocket_timeout=86400,
                 ping_interval=20,
                 ping_timeout=30,
                 ws_protocols=None,
                 use_proxy_headers=False,
                 use_proxy_proto_header=False,
                 use_x_sendfile=False):
        self.application = ApplicationManager(application)
        self.root_path = root_path

        self.http_timeout = http_timeout
        self.websocket_timeout = websocket_timeout
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.ws_protocols = ws_protocols
        self.use_proxy_headers = use_proxy_headers
        self.use_proxy_proto_header = use_proxy_proto_header
        self.use_x_sendfile = use_x_sendfile

        resource.Resource.__init__(self)

    def stop(self):
        return self.application.stop()

    def dispatch_websocket(self, request, base_scope):
        wsfactory = ASGIWebSocketServerFactory(application=self.application,
                                               base_scope=base_scope,
                                               idle_timeout=self.websocket_timeout,
                                               protocols=self.ws_protocols)

        wsfactory.setProtocolOptions(autoPingInterval=self.ping_interval,
                                     autoPingTimeout=self.ping_timeout)
        wsfactory.startFactory()
        return WebSocketResource(wsfactory).render(request)

    def dispatch_http(self, request, base_scope):
        return ASGIHTTPResource(application=self.application,
                                base_scope=base_scope,
                                timeout=self.http_timeout,
                                use_x_sendfile=self.use_x_sendfile).render(request)

    def render(self, request):
        path = [b''] + request.postpath
        path = '/'.join(p.decode('utf-8') for p in path)

        if b'?' in request.uri:
            query_string = request.uri.split(b'?', 1)[1]
        else:
            query_string = ''

        is_websocket = False
        headers = []
        for name, values in request.requestHeaders.getAllRawHeaders():
            # Prevent CVE-2015-0219
            if b"_" in name:
                continue

            name = name.lower()
            for value in values:
                headers.append([name, value])
                if name == b'upgrade' and value.lower() == b'websocket':
                    is_websocket = True

        if hasattr(request.client, 'host') and hasattr(request.client, 'port'):
            client_info = [request.client.host, request.client.port]
            server_info = [request.host.host, request.host.port]
        else:
            client_info = None
            server_info = None

        if self.use_proxy_headers:
            proxy_forwarded_host = request.requestHeaders.getRawHeaders(b"x-forwarded-for", [b""])[0].split(b",")[0].strip()
            proxy_forwarded_port = request.requestHeaders.getRawHeaders(b"x-forwarded-port", [b""])[0].split(b",")[0].strip()

            if proxy_forwarded_host:
                port = 0
                if proxy_forwarded_port:
                    try:
                        port = int(proxy_forwarded_port)
                    except ValueError:
                        pass

                client_info = [proxy_forwarded_host.decode('utf-8'), port]

        if self.use_proxy_proto_header:
            headers.append([b'x-forwarded-proto', b'http%s' % (request.isSecure() and b's' or b'')])

        # build base payload used by both websocket and normal as handshake
        base_scope = {
            'path': path,
            'query_string': query_string,
            'root_path': self.root_path,
            'headers': headers,
            'client': client_info,
            'server': server_info,
            '_ssl': request.isSecure() and 's' or '',
        }

        if is_websocket:
            return self.dispatch_websocket(request, base_scope)
        else:
            return self.dispatch_http(request, base_scope)

        return server.NOT_DONE_YET
