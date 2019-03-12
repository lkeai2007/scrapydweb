# coding: utf8
import logging
import re

from flask import current_app as app
from flask import g, request, url_for
from flask.views import View
from logparser import __version__ as LOGPARSER_VERSION

from .__version__ import __version__ as SCRAPYDWEB_VERSION
from .common import get_now_string, get_response_from_view, handle_metadata, handle_slash, json_dumps, session
from .vars import (ALLOWED_SCRAPYD_LOG_EXTENSIONS, DEMO_PROJECTS_PATH, DEPLOY_PATH, EMAIL_TRIGGER_KEYS, PARSE_PATH,
                   LEGAL_NAME_PATTERN, SCHEDULE_PATH, STATE_PAUSED, STATE_RUNNING, STATS_PATH, STRICT_NAME_PATTERN)
from .utils.scheduler import scheduler


class MyView(View):
    SCRAPYDWEB_VERSION = SCRAPYDWEB_VERSION
    LOGPARSER_VERSION = LOGPARSER_VERSION

    DEMO_PROJECTS_PATH = DEMO_PROJECTS_PATH
    DEPLOY_PATH = DEPLOY_PATH
    PARSE_PATH = PARSE_PATH
    SCHEDULE_PATH = SCHEDULE_PATH
    STATS_PATH = STATS_PATH

    OK = 'ok'
    ERROR = 'error'
    NA = 'N/A'
    INFO = 'info'
    WARN = 'warning'
    DEFAULT_LATEST_VERSION = 'default: the latest version'
    LEGAL_NAME_PATTERN = LEGAL_NAME_PATTERN
    STRICT_NAME_PATTERN = STRICT_NAME_PATTERN
    EMAIL_TRIGGER_KEYS = EMAIL_TRIGGER_KEYS

    methods = ['GET', 'POST']

    def __init__(self, *args, **kwargs):
        self.logger = logging.getLogger(self.__class__.__name__)
        # Not in the config file
        self.DEFAULT_SETTINGS_PY_PATH = app.config['DEFAULT_SETTINGS_PY_PATH']
        self.SCRAPYDWEB_SETTINGS_PY_PATH = app.config['SCRAPYDWEB_SETTINGS_PY_PATH']
        self.MAIN_PID = app.config['MAIN_PID']
        self.LOGPARSER_PID = app.config['LOGPARSER_PID']
        self.POLL_PID = app.config['POLL_PID']

        # System
        self.DEBUG = app.config.get('DEBUG', False)
        self.VERBOSE = app.config.get('VERBOSE', False)

        _level = logging.DEBUG if self.VERBOSE else logging.WARNING
        self.logger.setLevel(_level)
        logging.getLogger("requests").setLevel(_level)
        logging.getLogger("urllib3").setLevel(_level)

        # if request.view_args:
        #     self.logger.debug('view_args of %s\n%s', request.url, self.json_dumps(request.view_args))
        if request.args:
            self.logger.debug('request.args of %s\n%s', request.url, self.json_dumps(request.args))
        if request.form:
            self.logger.debug('request.form from %s\n%s', request.url, self.json_dumps(request.form))
        if request.files:
            self.logger.debug('request.files from %s\n\n    %s\n', request.url, request.files)

        # ScrapydWeb
        self.SCRAPYDWEB_BIND = app.config.get('SCRAPYDWEB_BIND', '0.0.0.0')
        self.SCRAPYDWEB_PORT = app.config.get('SCRAPYDWEB_PORT', 5000)

        self.ENABLE_AUTH = app.config.get('ENABLE_AUTH', False)
        self.USERNAME = app.config.get('USERNAME', '')
        self.PASSWORD = app.config.get('PASSWORD', '')

        self.ENABLE_HTTPS = app.config.get('ENABLE_HTTPS', False)
        self.CERTIFICATE_FILEPATH = app.config.get('CERTIFICATE_FILEPATH', '')
        self.PRIVATEKEY_FILEPATH = app.config.get('PRIVATEKEY_FILEPATH', '')

        self.URL_SCRAPYDWEB = app.config.get('URL_SCRAPYDWEB', 'http://127.0.0.1:5000')

        # Scrapy
        self.SCRAPY_PROJECTS_DIR = app.config.get('SCRAPY_PROJECTS_DIR', '') or self.DEMO_PROJECTS_PATH

        # Scrapyd
        self.SCRAPYD_SERVERS = app.config.get('SCRAPYD_SERVERS', []) or ['127.0.0.1:6800']
        self.SCRAPYD_SERVERS_AMOUNT = len(self.SCRAPYD_SERVERS)
        self.SCRAPYD_SERVERS_GROUPS = app.config.get('SCRAPYD_SERVERS_GROUPS', []) or ['']
        self.SCRAPYD_SERVERS_AUTHS = app.config.get('SCRAPYD_SERVERS_AUTHS', []) or [None]

        self.LOCAL_SCRAPYD_SERVER = app.config.get('LOCAL_SCRAPYD_SERVER', '')
        self.SCRAPYD_LOGS_DIR = app.config.get('SCRAPYD_LOGS_DIR', '')
        self.SCRAPYD_LOG_EXTENSIONS = (app.config.get('SCRAPYD_LOG_EXTENSIONS', [])
                                       or ALLOWED_SCRAPYD_LOG_EXTENSIONS)

        # LogParser
        self.ENABLE_LOGPARSER = app.config.get('ENABLE_LOGPARSER', True)
        self.BACKUP_STATS_JSON_FILE = app.config.get('BACKUP_STATS_JSON_FILE', True)

        # Timer Tasks
        self.scheduler = scheduler
        self.JOBS_SNAPSHOT_INTERVAL = app.config.get('JOBS_SNAPSHOT_INTERVAL', 300)

        # Page Display
        self.SHOW_SCRAPYD_ITEMS = app.config.get('SHOW_SCRAPYD_ITEMS', True)
        self.SHOW_JOBS_JOB_COLUMN = app.config.get('SHOW_JOBS_JOB_COLUMN', False)
        self.JOBS_FINISHED_JOBS_LIMIT = app.config.get('JOBS_FINISHED_JOBS_LIMIT', 0)
        self.JOBS_RELOAD_INTERVAL = app.config.get('JOBS_RELOAD_INTERVAL', 300)
        self.DAEMONSTATUS_REFRESH_INTERVAL = app.config.get('DAEMONSTATUS_REFRESH_INTERVAL', 10)

        # Email Notice
        self.ENABLE_EMAIL = app.config.get('ENABLE_EMAIL', False)
        self.POLL_ROUND_INTERVAL = app.config.get('POLL_ROUND_INTERVAL', 300)
        self.POLL_REQUEST_INTERVAL = app.config.get('POLL_REQUEST_INTERVAL', 10)
        self.SMTP_SERVER = app.config.get('SMTP_SERVER', '')
        self.SMTP_PORT = app.config.get('SMTP_PORT', 0)
        self.SMTP_OVER_SSL = app.config.get('SMTP_OVER_SSL', False)
        self.SMTP_CONNECTION_TIMEOUT = app.config.get('SMTP_CONNECTION_TIMEOUT', 10)
        self.FROM_ADDR = app.config.get('FROM_ADDR', '')
        self.TO_ADDRS = app.config.get('TO_ADDRS', [])
        self.EMAIL_USERNAME = app.config.get('EMAIL_USERNAME', '') or self.FROM_ADDR
        self.EMAIL_PASSWORD = app.config.get('EMAIL_PASSWORD', '')

        self.EMAIL_KWARGS = dict(
            smtp_server=self.SMTP_SERVER,
            smtp_port=self.SMTP_PORT,
            smtp_over_ssl=self.SMTP_OVER_SSL,
            smtp_connection_timeout=self.SMTP_CONNECTION_TIMEOUT,
            email_username=self.EMAIL_USERNAME,
            email_password=self.EMAIL_PASSWORD,
            from_addr=self.FROM_ADDR,
            to_addrs=self.TO_ADDRS,
            subject='subject',
            content='content'
        )

        self.EMAIL_WORKING_DAYS = app.config.get('EMAIL_WORKING_DAYS', [])
        self.EMAIL_WORKING_HOURS = app.config.get('EMAIL_WORKING_HOURS', [])
        self.ON_JOB_RUNNING_INTERVAL = app.config.get('ON_JOB_RUNNING_INTERVAL', 0)
        self.ON_JOB_FINISHED = app.config.get('ON_JOB_FINISHED', False)
        # ['CRITICAL', 'ERROR', 'WARNING', 'REDIRECT', 'RETRY', 'IGNORE']
        for key in self.EMAIL_TRIGGER_KEYS:
            setattr(self, 'LOG_%s_THRESHOLD' % key, app.config.get('LOG_%s_THRESHOLD' % key, 0))
            setattr(self, 'LOG_%s_TRIGGER_STOP' % key, app.config.get('LOG_%s_TRIGGER_STOP' % key, False))
            setattr(self, 'LOG_%s_TRIGGER_FORCESTOP' % key, app.config.get('LOG_%s_TRIGGER_FORCESTOP' % key, False))

        # Other attributes not from config
        self.view_args = request.view_args
        self.node = self.view_args['node']
        assert 0 < self.node <= self.SCRAPYD_SERVERS_AMOUNT, \
            'node index error: %s, which should be between 1 and %s' % (self.node, self.SCRAPYD_SERVERS_AMOUNT)
        self.SCRAPYD_SERVER = self.SCRAPYD_SERVERS[self.node - 1]
        self.IS_LOCAL_SCRAPYD_SERVER = self.SCRAPYD_SERVER == self.LOCAL_SCRAPYD_SERVER
        self.GROUP = self.SCRAPYD_SERVERS_GROUPS[self.node - 1]
        self.AUTH = self.SCRAPYD_SERVERS_AUTHS[self.node - 1]

        ua = request.headers.get('User-Agent', '')
        m_mobile = re.search(r'Android|webOS|iPad|iPhone|iPod|BlackBerry|IEMobile|Opera Mini', ua, re.I)
        self.IS_MOBILE = True if m_mobile else False

        m_ipad = re.search(r'iPad', ua, re.I)
        self.IS_IPAD = True if m_ipad else False

        # http://werkzeug.pocoo.org/docs/0.14/utils/#module-werkzeug.useragents
        # /site-packages/werkzeug/useragents.py
        browser = request.user_agent.browser or ''  # lib requests GET: None
        m_edge = re.search(r'Edge', ua, re.I)
        self.IS_IE_EDGE = True if (browser == 'msie' or m_edge) else False

        self.USE_MOBILEUI = request.args.get('ui', '') == 'mobile'
        self.UI = 'mobile' if self.USE_MOBILEUI else None
        self.GET = request.method == 'GET'
        self.POST = request.method == 'POST'

        self.FEATURES = ''
        self.FEATURES += 'A' if self.ENABLE_AUTH else '-'
        self.FEATURES += 'D' if handle_metadata().get('jobs_style') == 'database' else 'C'
        self.FEATURES += 'd' if self.SCRAPY_PROJECTS_DIR != self.DEMO_PROJECTS_PATH else '-'
        self.FEATURES += 'E' if self.ENABLE_EMAIL else '-'
        self.FEATURES += 'L' if self.ENABLE_LOGPARSER else '-'
        self.FEATURES += 'M' if self.USE_MOBILEUI else '-'
        self.FEATURES += 'P' if self.IS_MOBILE else '-'
        self.FEATURES += 'S' if self.ENABLE_HTTPS else '-'
        self.any_running_apscheduler_jobs = any(job.next_run_time
                                                for job in self.scheduler.get_jobs(jobstore='default'))
        if self.scheduler.state == STATE_PAUSED:
            self.FEATURES += '-'
        elif self.any_running_apscheduler_jobs:
            self.FEATURES += 'T'
        else:
            self.FEATURES += 't'

        self.template_fail = 'scrapydweb/fail_mobileui.html' if self.USE_MOBILEUI else 'scrapydweb/fail.html'
        self.update_g()

    @staticmethod
    def get_now_string(allow_space=False):
        return get_now_string(allow_space=allow_space)

    def get_response_from_view(self, url, as_json=False):
        auth = (self.USERNAME, self.PASSWORD) if self.ENABLE_AUTH else None
        return get_response_from_view(url, auth=auth, as_json=as_json)

    def get_selected_nodes(self):
        selected_nodes = []
        for n in range(1, self.SCRAPYD_SERVERS_AMOUNT + 1):
            if request.form.get(str(n)) == 'on':
                selected_nodes.append(n)
        return selected_nodes

    @staticmethod
    def handle_slash(string):
        return handle_slash(string)

    @staticmethod
    def json_dumps(obj, sort_keys=True, indent=4, ensure_ascii=False):
        return json_dumps(obj, sort_keys=sort_keys, indent=indent, ensure_ascii=ensure_ascii)

    @staticmethod
    def remove_microsecond(dt):
        return str(dt)[:19]

    def make_request(self, url, data=None, auth=None, as_json=True, dumps_json=True, timeout=60):
        """
        :param url: url to make request
        :param data: None or a dict object to post
        :param timeout: timeout when making request, in seconds
        :param as_json: return a dict object if set True, else text
        :param auth: None or (username, password) for basic auth
        :param dumps_json: whether to dumps the json response when as_json is set to True
        """
        try:
            if 'addversion.json' in url and data:
                self.logger.debug(">>>>> POST %s", url)
                self.logger.debug(self.json_dumps(dict(project=data['project'], version=data['version'],
                                                  egg="%s bytes binary egg file" % len(data['egg']))))
            else:
                self.logger.debug(">>>>> %s %s", 'POST' if data else 'GET', url)
                if data:
                    self.logger.debug("POST data: %s", self.json_dumps(data))

            if data:
                r = session.post(url, data=data, auth=auth, timeout=timeout)
            else:
                r = session.get(url, auth=auth, timeout=timeout)
            r.encoding = 'utf8'
        except Exception as err:
            # self.logger.error('!!!!! %s %s' % (err.__class__.__name__, err))
            self.logger.error("!!!!! error with %s: %s", url, err)
            if as_json:
                r_json = dict(url=url, auth=auth, status_code=-1, status=self.ERROR,
                              message=str(err), when=self.get_now_string(True))
                return -1, r_json
            else:
                return -1, str(err)
        else:
            if as_json:
                r_json = {}
                try:
                    # listprojects would get 502 html when Scrapyd server reboots
                    r_json = r.json()  # PY3: json.decoder.JSONDecodeError  PY2: exceptions.ValueError
                except ValueError as err:  # issubclass(JSONDecodeError, ValueError)
                    self.logger.error("Fail to decode json from %s: %s", url, err)
                    r_json = dict(status=self.ERROR, message=r.text)
                finally:
                    # Scrapyd in Python2: Traceback (most recent call last):\\n
                    # Scrapyd in Python3: Traceback (most recent call last):\r\n
                    message = r_json.get('message', '')
                    if message:
                        r_json['message'] = re.sub(r'\\n', '\n', message)
                    r_json.update(dict(url=url, auth=auth, status_code=r.status_code, when=self.get_now_string(True)))
                    status = r_json.setdefault('status', self.NA)
                    if r.status_code != 200 or status != self.OK:
                        self.logger.error("!!!!! (%s) %s: %s", r.status_code, status, url)
                    else:
                        self.logger.debug("<<<<< (%s) %s: %s", r.status_code, status, url)
                    if dumps_json:
                        self.logger.debug("Got json from %s: %s", url, self.json_dumps(r_json))
                    else:
                        self.logger.debug("Got keys from (%s) %s %s: %s",
                                          r_json.get('status_code'), r_json.get('status'), url, r_json.keys())

                    return r.status_code, r_json
            else:
                if r.status_code == 200:
                    _text = r.text[:100] + '......' + r.text[-100:] if len(r.text) > 200 else r.text
                    self.logger.debug("<<<<< (%s) %s\n%s", r.status_code, url, repr(_text))
                else:
                    self.logger.error("!!!!! (%s) %s\n%s", r.status_code, url, r.text)

                return r.status_code, r.text

    def update_g(self):
        # g lifetime: every single request
        # Note that use inject_variable() in View class would cause memory leak, issue #14
        g.IS_MOBILE = self.IS_MOBILE
        g.url_jobs_list = [url_for('jobs', node=node, ui=self.UI)
                           for node in range(1, self.SCRAPYD_SERVERS_AMOUNT + 1)]
        # For base.html
        if not self.USE_MOBILEUI:
            g.url_daemonstatus = url_for('api', node=self.node, opt='daemonstatus')
            g.url_menu_servers = url_for('servers', node=self.node)
            g.url_menu_jobs = url_for('jobs', node=self.node)
            g.url_menu_tasks = url_for('tasks', node=self.node)
            g.url_menu_deploy = url_for('deploy', node=self.node)
            g.url_menu_schedule = url_for('schedule', node=self.node)
            g.url_menu_projects = url_for('projects', node=self.node)
            g.url_menu_items = url_for('items', node=self.node)
            g.url_menu_logs = url_for('logs', node=self.node)
            g.url_menu_parse = url_for('parse.upload', node=self.node)
            g.url_menu_settings = url_for('settings', node=self.node)
            g.url_menu_mobileui = url_for('index', node=self.node, ui='mobile')
            g.scheduler_state_paused = self.scheduler.state == STATE_PAUSED and self.any_running_apscheduler_jobs
            g.scheduler_state_running = self.scheduler.state == STATE_RUNNING and self.any_running_apscheduler_jobs


class MetadataView(MyView):

    def __init__(self):
        super(self.__class__, self).__init__()

    def dispatch_request(self, **kwargs):
        return self.json_dumps(handle_metadata())
