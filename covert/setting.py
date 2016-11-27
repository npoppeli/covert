# -*- coding: utf-8 -*-
"""Global settings, i.e. settings shared by all modules.

Use like this, to make clear which module defines global variables:
    from covert import setting
    setting.models['Item'] = ...

Only in cases where performance matters, save one dictionary lookup with:
    from covert.setting import routes
    for route in routes:
    ....
"""

# version number of package
__version__ = '0.7'

# configuration
content   = None # (static) content directory
layout    = None # layout (template) directory
site      = None # site directory
models    = {}
views     = {}
language  = ''
languages = ['en', 'nl', 'sv']
config    = {} # configuration dictionary
debug     = False
verbose   = False

# storage
store_connection = None # connection for database
store_db         = None # database
store_dbname     = ''   # name of database

# routes
routes    = []
patterns  = {}
templates = {}
labels    = {}
icons     = {}
