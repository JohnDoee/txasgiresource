from __future__ import unicode_literals

import logging
import time

from twisted.internet import defer, reactor

from .scheduler import Scheduler
from .utils import TimeoutException, random_str, timeout_defer

logger = logging.getLogger(__name__)


class StoppedManagerException(Exception):
    pass


class Channel(object):
    """
    Abstraction to handle a bit of the logic surrounding a channel
    """
    def __init__(self, manager, reply_channel, reply_timeout):
        self.manager = manager
        self.reply_channel = reply_channel
        self.reply_timeout = reply_timeout
        self.defer = defer.Deferred()

    @defer.inlineCallbacks
    def get_reply(self):
        """
        Get a defer that is called with either a timeout exception or a
        value from the channel.
        """
        if self.reply_timeout:
            value = yield timeout_defer(self.reply_timeout, self.defer)
        else:
            value = yield self.defer
        self.defer = defer.Deferred()

        defer.returnValue(value)

    def cleanup(self):
        if not self.defer.called and self.defer.callbacks:
            self.defer.cancel()

    def finished(self):
        self.manager.remove_channel(self.reply_channel)

    def send(self, channel, payload):
        """Send a message to a channel"""
        self.manager.send(channel, payload)


class ChannelLayerManager(object):
    Timeout = TimeoutException

    def __init__(self, channel_layer, start_scheduler=True):
        self.channel_layer = channel_layer
        self.ChannelFull = channel_layer.ChannelFull
        self.send_channel =  'txasgi.response.%s!' % random_str()
        self._stop = False
        self.stopped = defer.Deferred()  # defer to add callback to, to get reply when manager is finished

        self._channels = {}
        self._pull_channels = set()

        if start_scheduler:
            self.scheduler = Scheduler(self)
            self.scheduler.start()
        else:
            self.scheduler = None

        self.puller()

    @defer.inlineCallbacks
    def stop(self):
        """Stop the manager from pulling more messages"""
        if self.scheduler:
            self.scheduler.stop()

        self._stop = True

        for channel in list(self._channels.keys()):
            self.remove_channel(channel)

        yield self.stopped

    def _puller(self):
        logger.debug('Starting puller loop')
        while True:
            if not reactor.running or self._stop:
                logger.debug('Puller loop dying')
                reactor.callFromThread(self.stopped.callback, None)
                return

            channels = [self.send_channel] + list(self._pull_channels)
            if not channels:
                time.sleep(0.05)
                continue

            channel, message = self.channel_layer.receive(channels, block=False)
            if not channel:
                time.sleep(0.01)
                continue
            logger.debug('We got message on channel: %s' % (channel, ))

            reactor.callFromThread(self.handle_reply, channel, message)

    def handle_reply(self, channel, message):
        if channel not in self._channels:
            logger.warning('Got reply to a non-exisistant channel: %s' % (channel, ))
            return

        channel = self._channels[channel]
        channel.defer.callback(message)

    def remove_channel(self, channel):
        channel = self._channels.pop(channel, None)
        self._pull_channels.discard(channel)
        if channel:
            channel.cleanup()

    def puller(self):
        reactor.callInThread(self._puller)

    def new_channel(self, prefix=None):
        """Get a new channel name of a given type"""
        if prefix:
            return prefix + random_str()
        else:
            return self.send_channel + random_str()

    def get_channel(self, timeout=None, channel_name=None):
        """Get a channel that can be pulled from of type channel_type"""
        if self._stop:
            raise StoppedManagerException()

        if channel_name:
            reply_channel = channel_name
            self._pull_channels.add(channel_name)
        else:
            reply_channel = self.new_channel()

        self._channels[reply_channel] = channel = Channel(self, reply_channel, timeout)

        return channel

    def send(self, channel, payload):
        self.channel_layer.send(channel, payload)
