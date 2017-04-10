from __future__ import unicode_literals

import logging

from autobahn.twisted.websocket import WebSocketServerFactory, WebSocketServerProtocol
from twisted.internet import defer
from twisted.protocols import policies

from .utils import sleep

logger = logging.getLogger(__name__)

SEND_CHANNEL_SLEEP_DELAY = 0.05
SEND_CHANNEL_RETRY_COUNT = 3


class ASGIWebSocketServerProtocol(WebSocketServerProtocol, policies.TimeoutMixin):
    order = 0
    accepted = False
    opened = False
    accept_promise = None

    def onConnect(self, request):
        self.channel = self.factory.manager.get_channel(self.factory.idle_timeout)
        self.opened = True

        channel_payload = self.factory.channel_base_payload
        channel_payload['scheme'] = 'ws%s' % (channel_payload.pop('_ssl'))
        channel_payload['reply_channel'] = self.channel.reply_channel

        self.order = channel_payload['order'] = 0

        try:
            self.channel.send('websocket.connect', channel_payload)
        except self.factory.manager.ChannelFull:
            logger.debug('Channel full')
            self.sendClose(self.CLOSE_STATUS_CODE_TRY_AGAIN_LATER)
            return

        self.setTimeout(self.factory.idle_timeout)
        self.accept_promise = defer.Deferred()

        self.send_replies()

        return self.accept_promise

    @defer.inlineCallbacks
    def send_replies(self):
        while True:
            try:
                reply = yield self.channel.get_reply()
            except self.factory.manager.Timeout:
                logger.debug('We hit a timeout')
                self.dropConnection(abort=True)
                break
            except defer.CancelledError:
                self.dropConnection(abort=True)
                break

            if not self.accepted:
                if reply.get('accept', True):
                    logger.debug('Accepting websocket connection')
                    self.accepted = True
                    self.accept_promise.callback(None)
                else:
                    logger.debug('Denying websocket connection')
                    self.sendClose()
                    break

            if reply.get('binary'):
                self.sendMessage(reply['binary'], True)

            if reply.get('text'):
                self.sendMessage(reply['text'].encode('utf8'), False)

            if reply.get('close'):
                self.sendClose()
                break

            self.resetTimeout()

    @defer.inlineCallbacks
    def onMessage(self, payload, isBinary):
        if not self.accepted:
            defer.returnValue(None)

        self.resetTimeout()

        self.order += 1

        channel_payload = {
            'reply_channel': self.channel.reply_channel,
            'path': self.factory.channel_base_payload['path'],
            'order': self.order,
        }

        if isBinary:
            channel_payload['bytes'] = payload
        else:
            channel_payload['text'] = payload.decode('utf8')

        for i in range(1, SEND_CHANNEL_RETRY_COUNT + 1):
            try:
                self.channel.send('websocket.receive', channel_payload)
                logger.debug('Pushed received message to channel')
                break
            except self.factory.manager.ChannelFull:
                logger.debug('Channel full, retrying')
                yield sleep(i * SEND_CHANNEL_SLEEP_DELAY)[0]
        else:
            logger.debug('Channel full, killing connection')
            self.sendClose(self.CLOSE_STATUS_CODE_TRY_AGAIN_LATER)

    def onClose(self, wasClean, code, reason):
        if not self.opened:
            return

        logger.info('Called onClose')
        self.order += 1

        channel_payload = {
            'reply_channel': self.channel.reply_channel,
            'path': self.factory.channel_base_payload['path'],
            'order': self.order,
            'code': code,
        }

        try:
            self.channel.send('websocket.disconnect', channel_payload)
        except self.factory.manager.ChannelFull:
            logger.debug('Channel full')

        self.channel.finished()

    def timeoutConnection(self):
        logger.debug('Timeout from mixin')
        self.dropConnection(abort=True)


class ASGIWebSocketServerFactory(WebSocketServerFactory):
    protocol = ASGIWebSocketServerProtocol

    def __init__(self, *args, **kwargs):
        self.manager = kwargs.pop('manager')
        self.channel_base_payload = kwargs.pop('channel_base_payload')
        self.idle_timeout = kwargs.pop('idle_timeout')

        WebSocketServerFactory.__init__(self, *args, **kwargs)
