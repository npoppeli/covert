# -*- coding: utf-8 -*-
"""
covert.setting
--------------
Global settings, shared by all modules. The application registry, in fact.
"""

version = '0.1'

storage_name = ''
storage_connection = None
storage_database = None

content = None # (static) content directory
layout = None # layout directory
routes = []
models = {}
views = {}
template = {}