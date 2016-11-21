# -*- coding: utf-8 -*-
"""Covert: COntent as VERsatile uniTs

Copyright: ...
License: ...

Attributes:
    * setting:       module object with global settings

Functions:
    * read_config:   read configuration file
    * parse_cmdline: parse command line
    * kernel_init:   initialize kernel
    * http_server:   development server based on Waitress
    * url_for:       create URL for route
    * show_dict:     pretty-print dictionary

Classes:
    * SwitchRouter:  WSGI front-end application that dispatches to WSGI applications for
    *                static files, HTML fragment, HTML page and JSON
    * MapRouter:     WSGI application that dispatches on the basis of PATH_INFO
    * PageRouter:    sub-class of MapRouter for HTML pages
    * JSONRouter:    sub-class of MapRouter for JSON
    * route:         decorator for methods in an ItemView class
    * BareItemView:  view that does not define routes
    * ItemView:      view with routes for the Atom Publishing protocol
    * ItemRef:       base class for item references
"""

from .           import setting
from .config     import read_config, parse_cmdline, kernel_init
from .controller import http_server, SwitchRouter, MapRouter, PageRouter, JSONRouter
from .model      import ItemRef
from .view       import route, BareItemView, ItemView, url_for, show_dict, encode_dict
