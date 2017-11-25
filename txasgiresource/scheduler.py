from __future__ import unicode_literals

import logging

import six
from apscheduler.schedulers.twisted import TwistedScheduler
from twisted.internet import defer

logger = logging.getLogger(__name__)

SCHEDULE_ARGUMENTS = {
    'interval': {
        'weeks': int,
        'days': int,
        'hours': int,
        'minutes': int,
        'seconds': int,
        'start_date': six.text_type,
        'end_date': six.text_type,
        'timezone': six.text_type,
    },
    'date': {
        'run_date': six.text_type,
        'timezone': six.text_type,
    },
    'cron': {
        'year': int,
        'week': int,
        'day': int,
        'week': int,
        'day_of_week': int,
        'hour': int,
        'minute': int,
        'second': int,
        'start_date': six.text_type,
        'end_date': six.text_type,
        'timezone': six.text_type,
    },
}


class Scheduler(object):
    channel = None

    def __init__(self, manager, channel_name='schedule', timeout=60 * 60 * 24):
        self.manager = manager
        self.channel_name = channel_name
        self.timeout = timeout

        self.channel = self.manager.get_channel(self.timeout, channel_name=self.channel_name)
        self.scheduler = TwistedScheduler()

    @defer.inlineCallbacks
    def start(self):
        logger.debug('Starting scheduler')
        self.scheduler.start()

        while True:
            try:
                logger.debug('Pulling...')
                job_action = yield self.channel.get_reply()
            except self.manager.Timeout:
                logger.debug('We hit a timeout in scheduler, not a lot of job activity.')
                continue
            except defer.CancelledError:
                defer.returnValue(None)

            if not job_action:
                logger.info('Empty job_action, killing scheduler')
                break

            logger.debug('We got a job: %r' % (job_action, ))

            method = job_action.pop('method', None)

            if method == 'add':
                missing_keys = {'id', 'trigger', 'reply_channel'} - set(job_action.keys())
                if missing_keys:
                    logger.warning('Missing keys in add schedule: %r' % (missing_keys, ))
                    continue

                job_id = job_action.pop('id')
                trigger = job_action.pop('trigger')
                reply_channel = job_action.pop('reply_channel')
                reply_args = job_action.pop('reply_args', {})

                if not reply_channel.startswith('schedule.'):
                    logger.warning('Reply channel must start with schedule., %r does not' % (reply_channel, ))
                    continue

                if isinstance(reply_channel, six.binary_type):
                    reply_channel = reply_channel.decode("ascii")

                if not isinstance(reply_args, dict):
                    logger.warning('reply_args not a dict')
                    continue

                if trigger not in SCHEDULE_ARGUMENTS:
                    logger.warning('Unknown trigger %s' % (trigger, ))
                    continue

                bad_args = False
                kwargs = SCHEDULE_ARGUMENTS[trigger]
                for k, v in job_action.items():
                    if k not in kwargs:
                        logger.warning('Unknown argument %s for schedule %s' % (k, trigger, ))
                        bad_args = True
                        break

                    if not isinstance(v, kwargs[k]):
                        logger.warning('Argument %s is of wrong type, should be %r' % (k, kwargs[k]))
                        bad_args = True
                        break

                if bad_args:
                    continue

                if self.scheduler.get_job(job_id):
                    logger.warning('Job %s already exist, skipping' % (job_id, ))
                    continue

                logger.debug('Scheduling new job with id:%s '
                             'reply_channel:%s args:%r schedule_args:%r'
                             % (job_id, reply_channel, reply_args, job_action))
                self.scheduler.add_job(self.launch_job,
                                       trigger,
                                       kwargs={'reply_channel': reply_channel, 'reply_args': reply_args},
                                       id=job_id,
                                       **job_action)
            elif method == 'remove':
                job_id = job_action.get('id')
                if not job_id:
                    logger.warning('Missing keys in remove schedule: id')
                    continue

                self.scheduler.remove_job(job_id)

    def launch_job(self, reply_channel, reply_args):
        logger.debug('Launching job on channel:%r args:%r' % (reply_channel, reply_args, ))
        self.manager.send(reply_channel, reply_args)

    def stop(self):
        self.scheduler.shutdown()
