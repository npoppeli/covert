# -*- coding: utf-8 -*-
"""
covert.setting
--------------
Global settings, shared by all modules.
Use like this, to make clear which module defines global variables:
  from covert import setting
  setting.models['Item'] = ...

Only in cases where performance matters, save one dictionary lookup with:
  from covert.setting import routes
  for route in routes:
    ....
"""

version          = '0.7'
store_connection = None # connection for database # TODO: make this thread-safe
store_db         = None # database
store_dbname     = ''   # name of database
content          = None # (static) content directory
layout           = None # layout (template) directory
site             = None # site directory
patterns         = {}
routes           = []
models           = {}
views            = {}
templates        = {}
labels           = {}
language         = ''
languages        = ['en', 'nl', 'sv'] # TODO: use Python locale functionality
icons            = {}
config           = {}
debug            = False