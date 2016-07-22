# -*- coding: utf-8 -*-
"""
covert.setting
--------------
Global settings, shared by all modules. The application registry, in fact.
"""

version          = '0.1'
store_connection = None # connection for database # TODO: make this thread-safe
store_db         = None # database
store_dbname     = ''   # name of database
content          = None # (static) content directory
layout           = None # layout (template) directory
site             = None # site directory
routes           = []
models           = {}
views            = {}
templates        = {}
config           = {}
debug            = False