from __future__ import unicode_literals

from asgiref.inmemory import ChannelLayer
from twisted.internet import defer
from twisted.trial.unittest import TestCase

from ..manager import ChannelLayerManager
from ..utils import sleep


class TestASGIScheduler(TestCase):
    def setUp(self):
        self.channel_layer = ChannelLayer()
        self.manager = ChannelLayerManager(self.channel_layer)
        self.scheduler = self.manager.scheduler

    @defer.inlineCallbacks
    def tearDown(self):
        yield self.manager.stop()

    @defer.inlineCallbacks
    def test_add_job(self):
        self.channel_layer.send(self.scheduler.channel_name, {
            'method': 'add',
            'id': 'job_id',
            'reply_channel': 'schedule.test',

            'trigger': 'interval',
            'weeks': 0,
            'days': 0,
            'hours': 0,
            'minutes': 0,
            'seconds': 0,

            'reply_args': {'a': 'b'},
        })

        for _ in range(15):
            _, message = self.channel_layer.receive(['schedule.test'])
            if message:
                break
            yield sleep(0.1)[0]
        else:
            self.fail('Never got reply to schedule')

        self.assertEqual(message, {'a': 'b'})

    @defer.inlineCallbacks
    def test_add_remove_job(self):
        self.channel_layer.send(self.scheduler.channel_name, {
            'method': 'add',
            'id': 'job_id',
            'reply_channel': 'schedule.test',

            'trigger': 'interval',
            'weeks': 10,

            'reply_args': {'a': 'b'},
        })

        yield sleep(0.1)[0]

        self.assertNotEqual(self.scheduler.scheduler.get_job('job_id'), None)

        self.channel_layer.send(self.scheduler.channel_name, {
            'method': 'remove',
            'id': 'job_id',
        })

        yield sleep(0.1)[0]

        self.assertEqual(self.scheduler.scheduler.get_job('job_id'), None)

    def test_remove_invalid_job(self):
        self.channel_layer.send(self.scheduler.channel_name, {
            'method': 'remove',
            'id': 'invalid_id',
        })
