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
    """read entire file, return content as one string"""
    with open(filename, 'rU') as f:
        text = ''.join(f.readlines())
    return text

def read_yaml_file(path, multi=False):
    """read file, return YAML content as (list of) document(s)"""
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
    """decode string s to JSON document"""
    return json.loads(html.unescape(s)) if s else {}

def encode_dict(d):
    """encode JSON document d to string"""
    return html.escape(json.dumps(d, separators=(',',':'), cls=ExtendedEncoder))

def show_dict(s):
    """encode JSON document d to pretty-printed string"""
    return json.dumps(s, separators=(',',':'), sort_keys=True, indent=2, cls=ExtendedEncoder)


class Trie:
    """Trie data structure

    Lightweight trie data structure, based on an example by James Tauber.
    A Trie is a radix or prefix tree, and can be used to represent a dictionary or
    classification scheme, for example.
    """
    def __init__(self):
        self.root = [None, None, {}]

    def __setitem__(self, path, value):
        node = self.root
        for edge in path:
            node = node[2].setdefault(edge, [None, None, {}])
        node[0] = value
