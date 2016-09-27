# -*- coding: utf-8 -*-
"""
covert
------
Main module of the COVERT framework, a publishing framework based on Webob and Chameleon,
and a variety of storage engines, e.g. MongoDB and RethinkDB.

The 'view' module defines the View class. Each View instance consists of one or more methods
(routes). Each route yields a tree structure that can be rendered to HTML, JSON or another format.

A route (view method) operates on one or more instances of a sub-class of the Item class.
The subclasses of Item are defined in the model of the application. More complicated routes
could (in theory) operate on items of different classes.

A route method is a pipeline, consisting of:
1. generator (get primary content, i.e. an Item, from the database)
2. transformer (transform into render tree; the same thing happens for the secondary content)
3. aggregator (all content is combined into a single document that can be rendered)
4. serializer (serialize to HTML, JSON or XML is done by templates)

When a route is called from a web page, three elements are relevant:

1. representation in the web page: button consisting of label, icon and CSS style;
2. HTTP request method and URL;
3. method or function performing the actual work.

The URL corresponding to a route is written as a pattern. Each route, i.e. each pattern,
has a unique identifier. This identifier is used to construct a URL from the components
of the item.

The URL pattern, method and template are attached to the method
or function by means of a decorator: @route(pattern, method, template)

There are three types of buttons:
1. normal button    (label, icon, action, enabled=True|False)
2. form button      (label, icon, action, name, value)
3. delete button    (label, icon, action, enabled=True|False)

Form buttons contain an action. The actions within one group of form buttons should be identical;
the first action is picked up as the action of the form.
The action is a URL or a JavaScript expression, e.g. confirmDelete(action). Defined in
/_static/script/site.js (can be done fancier with Dojo's dijit/Dialog)
The shape of a button (label, icon or both) is determined by the template that serializes the
page in which the button is embedded.
"""

from .config         import read_config, parse_cmdline, kernel_init
from .controller     import http_server, SwitchRouter, MapRouter, PageRouter, JSONRouter
from .layout         import read_templates
from .model          import mapdoc
from .report         import logger
from .view           import route, BareItemView, ItemView
from .               import setting
