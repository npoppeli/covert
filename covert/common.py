# -*- coding: utf-8 -*-
"""
covert.common
-----
Objects and functions common to two or more modules in the package.
"""

import json, os, os.path, datetime
import html
from bson.objectid import ObjectId
from yaml import load, load_all
try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader

# exceptions
class Error(Exception):
    def __init__(self, message):
        self.message = message
    def __str__(self):
        return repr(self.message)

# auxiliary functions
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

def str2int(s):
    try:
        i = int(s)
    except:
        i = 0
    return i

class ComplexEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (ObjectId, datetime.datetime, datetime.time, datetime.date)):
            return str(obj)
        else:
            return json.JSONEncoder.default(self, obj)

def decode_dict(s):
    return json.loads(html.unescape(s))

def encode_dict(s):
    return html.escape(json.dumps(s, separators=(',',':'), cls=ComplexEncoder))

def show_dict(s):
    return json.dumps(s, separators=(',',':'), cls=ComplexEncoder)

# lightweight Trie data structure, based on an example by James Tauber
# A Trie is a radix or prefix tree, and can be used to represent a dictionary, for example.
class Trie:
    def __init__(self):
        self.root = [None, None, {}]

    def __setitem__(self, path, value):
        node = self.root
        for edge in path:
            node = node[2].setdefault(edge, [None, None, {}])
        node[0] = value
