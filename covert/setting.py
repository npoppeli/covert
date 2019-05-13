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
__version__ = '0.10'

# configuration
content     = '' # relative path to static content
media       = '' # relative path to media storage
layout      = '' # relative layout to template directory
site        = '' # site directory
models      = {}
views       = {}
icons       = {}
language    = ''
languages   = ['en', 'nl', 'sv']
config      = {} # configuration dictionary
host        = ''
port        = 0
config_file = 'config' # name of configuration file
dbtype      = 'mongodb'
debug       = 0
nostore     = False # for 'dry runs'
tables      = False
verbose     = 0

# storage
store_connection = None    # connection for item database
store_db         = None    # item database
store_dbname     = ''      # name of item database
store_mdb        = None    # media database (CAS)

# routes
routes    = []
patterns  = {}
templates = {}
labels    = {}
icons     = {}
