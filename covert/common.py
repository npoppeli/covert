# -*- coding: utf-8 -*-
"""Objects and functions common to two or more modules in the package.

This includes JSON and YAML functions, but also reporting and logging.

For logging we use the 'logging' module. Logging levels are DEBUG, INFO, WARNING, ERROR,
CRITICAL. Covert uses logging level INFO by default, and DEBUG if called with --debug. Since the
Waitress package is one of the dependencies, we can re-use the logger object of that package.
The Waitress logger does not define handlers itself. It inherits the handler from the root logger.
"""

import gettext, json, logging
from os.path import dirname, join
from . import setting
from urllib.parse import urlparse, urljoin
from webob.exc import HTTPTemporaryRedirect
from yaml import load, load_all
try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader

# Logging
# basicConfig adds a StreamHandler with default Formatter to the root logger. This function
# does nothing if the root logger already has handlers configured for it.
logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)
logger = logging.getLogger('waitress')

# I18N
# After every update that involves strings:
#  pybabel extract *.py engine/*.py -o locales/covert.pot
#  pybabel update -i locales/covert.pot -D 'covert' -d locales
setting.locales = join(dirname(setting.__file__), 'locales')
print("C: install 'en' translation catalog from path", setting.locales)
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
    if not target or not is_safe_url(target):
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

class ExtendedEncoder(json.JSONEncoder):
    """JSON encoder that can handle all atom types"""
    def default(self, obj):
        if isinstance(obj, (dict, list, tuple, int, float, bool, str)):
            return json.JSONEncoder.default(self, obj)
        else:
            return str(obj)

def decode_dict(s):
    """Decode string to JSON document.

    Arguments:
        s (str): string in JSON notation

    Returns:
        list|dict: JSON document
    """
    return json.loads(s) if s else {}

def encode_dict(d):
    """Encode JSON document to string.

    Arguments:
        d (dict): JSON document

    Returns:
        str: content as one string
    """
    # return html.escape(json.dumps(d, separators=(',', ':'), cls=ExtendedEncoder))
    return json.dumps(d, separators=(',', ':'), cls=ExtendedEncoder)

def show_dict(d):
    """Encode JSON document to pretty-printed string.

    Arguments:
        d (dict): JSON document

    Returns:
        str: content as one pretty-printed string
    """
    return json.dumps(d, separators=(',',':'), sort_keys=True, indent=2, cls=ExtendedEncoder)

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

def show_value(s):
    if isinstance(s, list):
        return "[{}]".format(', '.join([str(el) for el in s]))
    else:
        return str(s)

def show_item3(label1, label2, label3, item1, item2, item3):
    fmt = "{:<15}: {!s:<35} {!s:<35} {!s:<35}"
    print(fmt.format('', label1, label2, label3))
    print('-' * 120)
    for key in sorted(set(item1.keys()) | set(item2.keys()) | set(item3.keys())):
        value1 = show_value(item1.get(key, '-'))
        value2 = show_value(item2.get(key, '-'))
        value3 = show_value(item3.get(key, '-'))
        if key == '_id' or (value1 == '' and value2 == '' and value3 == ''):
            continue
        print(fmt.format(key, value1, value2, value3))
    print('\n')

# Trie data structure: see http://jtauber.com/2005/02/trie.py for Python implementation
