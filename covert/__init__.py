# -*- coding: utf-8 -*-
"""Covert: COntent as VERsatile uniTs

Copyright: ...
License: ...

Attributes:
    setting:       global settings

Functions:
    read_config:   read configuration file
    parse_cmdline: parse command line
    kernel_init:   initialize kernel
    http_server:   development server based on Waitress

Classes:
    SwitchRouter:  WSGI front-end application that dispatches to WSGI applications for
        static files, HTML fragment, HTML page and JSON
    MapRouter:     WSGI application that dispatches on the basis of PATH_INFO
    PageRouter:    sub-class of MapRouter for HTML pages
    JSONRouter:    sub-class of MapRouter for JSON
    route:         decorator for methods in an ItemView class
    BareItemView:  view that does not define routes
    ItemView:      view with routes for the Atom Publishing protocol
"""

from .           import setting
from .config     import read_config, parse_cmdline, kernel_init
from .controller import http_server, SwitchRouter, MapRouter, PageRouter, JSONRouter
from .view       import route, BareItemView, ItemView
