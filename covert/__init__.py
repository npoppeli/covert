# -*- coding: utf-8 -*-
"""
covert
------
Main module of the COVERT framework, a publishing framework based on Webob and Chameleon,
and a variety of storage engines, e.g. RethinkDB and MongoDB.

The 'view' module defines the View class. Each View instance consists of one or more methods
(routes). Each route yields a tree structure that can be rendered to HTML,
JSON or another format.

A route method operates on one or more instances of a sub-class of the Item class. The subclasses
of Item are defined in the model of the application. More complicated actions can operate on
items of different classes.

A route method is a pipeline (a concept borrowed from Apache Cocoon):
1. generator (get primary content, i.e. a Node, from database)
2. transformer (transform into render array; the same thing happens for the secondary content)
3. aggregator (all content is combined into a single document that can be rendered)
4. serializer (serialize to Python dictionary

Serialization to HTML, JSON or XML is done by ...

When a route method is called from a web page, three elements are relevant:

1. representation in the web page: button consisting of label, icon and CSS style;
2. HTTP request: method and URL;
3. method or function performing the actual action.

The URL corresponding to a route is written as a pattern. Each route, i.e.
each pattern, has a unique identifier. This identifier is used to construct a URL from
a id, key or other field.

The name, style, method, URL pattern and pattern identifier are attached to the method
or function by means of a decorator: @route(pattern, method, template)

There are three types of buttons:
1. normal button    (name,   value, label, icon, enabled=True|False)
2. form button      (action,        label, icon)
3. delete button

The action is a URL or a JavaScript expression, e.g. confirmDelete(action).
Defined in /_static/script/site.js (can be done fancier with Dojo's dijit/Dialog)
Form buttons do not contain an action, since that is defined by the 'action'
attribute of the parent element 'form'.

The shape of a button (label, icon or both) is decided by the component that builds the
page in which the button is embedded.
"""

from .config         import read_config, parse_cmdline, kernel_init
from .controller     import http_server, SwitchRouter, MapRouter, PageRouter, JSONRouter
from .layout         import read_templates
from .model          import mapdoc
from .report         import logger
from .view           import route, BareItemView, ItemView
from .               import setting
