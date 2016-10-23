# -*- coding: utf-8 -*-
"""Objects and functions common to two or more modules in the package.
"""

import html, json
from yaml import load, load_all
try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader

# exceptions
class InternalError(Exception):
    """Internal error exception.

      Attributes:
          messsage (str): human-readable string describing the exception
      """
    def __init__(self, message):
        self.message = message
    def __str__(self):
        return repr(self.message)

# HTTP-related functions
# def is_safe_url(target, req):
#     host_url = urlparse(req.host_url)
#     test_url = urlparse(urljoin(req.host_url, target))
#     return test_url.scheme in ('http', 'https') and (host_url.netloc == test_url.netloc)

# def redirect_location(req):
#     if req.referrer and is_safe_url(req.referrer, req):
#         return req.referrer
#     else:
#         return ''

# def redirect_back(req, default):
#     target = req.params['_next']
#     if not target or not is_safe_url(target):
#         target = default
#     raise HTTPSeeOther(location=target)

# JSend
SUCCESS = 'success'
FAIL    = 'fail'
ERROR   = 'error'

# YAML-related functions
def read_file(filename):
    """Read entire text file.

    Arguments:
        filename (str): name of text file

    Returns:
        str: content as one string
    """
    with open(filename, 'rU') as f:
        text = ''.join(f.readlines())
    return text

def read_yaml_file(path, multi=False):
    """Read YAML file.

    Arguments:
        filename (str): name of YAML file
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

# JSON-related functions
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
    return json.loads(html.unescape(s)) if s else {}

def encode_dict(d):
    """Encode JSON document to string.

    Arguments:
        d (dict): JSON document

    Returns:
        str: content as one string
    """
    return html.escape(json.dumps(d, separators=(',',':'), cls=ExtendedEncoder))

def show_dict(d):
    """Encode JSON document to pretty-printed string.

    Arguments:
        d (dict): JSON document

    Returns:
        str: content as one pretty-printed string
    """
    return json.dumps(d, separators=(',',':'), sort_keys=True, indent=2, cls=ExtendedEncoder)

# Trie data structure: see http://jtauber.com/2005/02/trie.py for Python implementation
