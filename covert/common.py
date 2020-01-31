# -*- coding: utf-8 -*-
"""Objects and functions common to two or more modules in the package.

This includes JSON and YAML functions, but also reporting and logging.

For logging we use the 'logging' module. Logging levels are DEBUG, INFO,
WARNING, ERROR, CRITICAL. We use logging level INFO by default, and
DEBUG if called with --debug.
"""

import gettext, json, logging, sys, traceback
from datetime import datetime
from os import mkdir, getcwd
from os.path import dirname, join, exists
from . import setting
from urllib.parse import urlparse, urljoin
from webob.exc import HTTPTemporaryRedirect
from yaml import load, load_all
try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader

# In case we ever need a trie data structure:
# see http://jtauber.com/2005/02/trie.py for Python implementation

# Logging
# basicConfig adds a StreamHandler with default Formatter to the root logger. This
# function does nothing if the root logger already has handlers configured for it.
# This module is imported before the 'controller' module, which imports the 'waitress' module.
# The first call to basisConfig 'wins', and in theory that should be the one below.
logdir = getcwd() + '/log'  # assumption: cwd == site directory
if not exists(logdir):
    mkdir(logdir)
logfile = '{}/{}.log'.format(logdir, datetime.now().strftime("%Y%m%d"))
logging.basicConfig(filename=logfile, datefmt='%Y-%m-%d %H:%M:%S', style='{',
                    format='{asctime} {levelname:7}: {message}',
                    level=logging.INFO)
logger = logging.getLogger('covert')
print('covert.common: call logging.basicConfig; log to file {}'.format(logfile))

def exception_report(exc, ashtml=True):
    """Generate exception traceback, as plain text or HTML

    Arguments:
        exc    (Exception): exception object
        ashtml (bool)     : render as HTML (True) or plain text (False)

    Returns:
        str: exception report as plain or HTML text
    """
    exc_type, exc_value, exc_trace = sys.exc_info()
    title = _('Internal error')
    head = _('Traceback (most recent call last)')
    if ashtml:
        body = []
        for line in traceback.format_tb(exc_trace):
            body.extend(line.splitlines())
        tail = '{0}: {1}'.format(exc_type.__name__, str(exc_value))
        tree = {'title': title, 'head':head, 'body':body, 'tail':tail}
        return setting.templates['error'](tree)
    else:
        head = [title + '. ' + head]
        body = traceback.format_tb(exc_trace)
        tail = ['{0}: {1}'.format(exc_type.__name__, str(exc_value))]
        return '\n'.join(head+body+tail)

# I18N
# After every update that involves strings:
#  pybabel extract *.py engine/*.py -o locales/covert.pot
#  pybabel update -i locales/covert.pot -D 'covert' -d locales
setting.locales = join(dirname(setting.__file__), 'locales')
translator = gettext.translation('covert', localedir=setting.locales, languages=['en'])
_ = translator.gettext

# String handling
def escape_squote(s):
    """Escape single quotes in string `s`."""
    return s.replace("'", chr(92)+'u0027')

def escape_dquote(s):
    """Escape double quotes in string `s`."""
    return s.replace("'", chr(92)+'u0022')

def str2int(s):
    """Convert str to integer, or otherwise 0."""
    try:
        number = int(s)
    except:
        number = 0
    return number

# TODO: future extension
# Permissions (privileges)
CATEGORY_CREATE = 0
CATEGORY_READ   = 1
CATEGORY_UPDATE = 2
CATEGORY_DELETE = 3

# Exceptions
class InternalError(Exception):
    """Internal error exception.

      Attributes:
          message (str): human-readable string describing the exception
      """
    def __init__(self, message):
        self.message = message
    def __str__(self):
        return repr(self.message)

# HTTP-related functions
def is_safe_url(target, request):
    host_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and (host_url.netloc == test_url.netloc)

def redirect_location(request):
    if request.referrer and is_safe_url(request.referrer, request):
        return request.referrer
    else:
        return ''

def redirect_back(request, default):
    target = request.params['_next']
    if not target or not is_safe_url(target, request):
        target = default
    raise HTTPTemporaryRedirect(location=target)

# YAML-related functions
def read_file(filename):
    """Read entire text file.

    Arguments:
        filename (str): name of text file

    Returns:
        str: content as one string
    """
    with open(filename, 'r') as f:
        text = ''.join(f.readlines())
    return text

def read_yaml_file(path, multi=False):
    """Read YAML file.

    Arguments:
        path(str)   : name of YAML file
        multi (bool): True if file can contain multiple documents

    Returns:
        list|dict: list of documents (multi is True) or single document (otherwise)
    """
    with open(path, 'r') as f:
        if multi:
            result = list(load_all(f, Loader=Loader))
        else:
            result = load(f, Loader=Loader)
    return result

def write_file(path, text):
    """Write text file.

    Arguments:
        path (str): name of text file
        text (str): string to be written

    Returns:
        None
    """
    with open(path, 'w') as f:
        f.write(text)

# JSON-related functions
# JSend
SUCCESS = 'success'
FAIL    = 'fail'
ERROR   = 'error'

class EncodeWithStrFallback(json.JSONEncoder):
    """JSON encoder that can handle all atom types"""
    def default(self, obj):
        if isinstance(obj, (dict, list, tuple, int, float, bool, str)):
            return json.JSONEncoder.default(self, obj)
        else:
            return str(obj)

class EncodeWithReprFallback(json.JSONEncoder):
    """Another JSON encoder that can handle all atom types"""
    def default(self, obj):
        if isinstance(obj, (dict, list, tuple, int, float, bool, str)):
            return json.JSONEncoder.default(self, obj)
        else:
            return repr(obj)

def decode_dict(s):
    """Decode string in JSON form to dictionary.

    Arguments:
        s (str): string in JSON form

    Returns:
        list|dict: JSON document
    """
    return json.loads(s) if s else {}

def encode_dict(d):
    """Encode document (dictionary) to JSON string.

    Arguments:
        d (dict): document

    Returns:
        str: content as one string in JSON form
    """
    # return html.escape(json.dumps(d, separators=(',', ':'), cls=ExtendedEncoder))
    return json.dumps(d, separators=(',', ':'), cls=EncodeWithStrFallback)

def show_dict(d):
    """Encode document (dictionary) to pretty-printed JSON string.

    Arguments:
        d (dict): document

    Returns:
        str: content as one string in JSON form, and with nice formatting
    """
    return json.dumps(d, separators=(',',':'), cls=EncodeWithReprFallback,
                      sort_keys=True, indent=2)

def show_document(d):
    return '\n'.join("{:<20}: {}".format(key, str(value)[0:80])
                     for key, value in d.items())

def read_json_file(path):
    """Read JSON file.

    Arguments:
        path (str): name of JSON file

    Returns:
        list|dict: list of documents or single document
    """
    with open(path, 'r') as f:
        text = ''.join(f.readlines())
    return json.loads(text)

def format_json_diff(a, b):
    """Format the difference between two items so that it is human-readable."""
    result = ''
    diff = a ^ b
    for key, value in diff.items():
        if not value:
            continue
        # TODO: translate `k` (field name) to application language
        details = '; '.join('{}: {}'.format(k, v) for k, v in value.items())
        if key == '$insert':
            result += "{}: {}. ".format(_('Inserted'), details)
        elif key == '$update':
            result += "{}: {}. ".format(_('Updated'), details)
        elif key == '$delete':
            result += "{}: {}. ".format(_('Deleted'), details)
    return result
