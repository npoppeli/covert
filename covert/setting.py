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
__version__ = '0.12'

# configuration
content     = '' # path to static content
media       = '' # path to media storage
layout      = '' # path to layout (template) directory
locales     = '' # path to locales directory
logfile     = '' # path to log file
site        = '' # site directory
models      = {}
views       = {}
language    = ''
languages   = ['en', 'nl', 'sv']
config      = {}       # configuration dictionary
config_file = 'config' # name of configuration file
debug       = 0
tables      = False
verbose     = 0

# storage
dbtype      = 'mongodb'
dbname      = ''      # name of item database
connection  = None    # connection for item database
item_db     = None    # item database
media_db    = None    # media database (CAS)
host        = ''      # host for item database
port        = 0       # port for item database
username    = ''      # username for item database
password    = ''      # password for item database
nostore     = False   # for 'dry runs'

# routes and buttons
routes      = []
patterns    = {}
templates   = {}
labels      = {}
icons       = {}
buttons     = {}
