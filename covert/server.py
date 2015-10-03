# -*- coding: utf-8 -*-
"""
covert.server
-----
Objects and functions related to WSGI and HTTP servers.
"""

import waitress, re, sys, traceback, json
# from paste.exceptions.errormiddleware import ErrorMiddleware
from webob import BaseRequest as Request, Response # performance of BaseRequest is better
from .view import action_map
from .common import Error
from .template import node, render
from .report import logger, print_node, print_doc
from .hook import hook_page_attachments, hook_page_top, hook_page_bottom

def http_server(app, **kwarg):
    logger.debug('starting HTTP server')
    # wrapped = ErrorMiddleware(app, debug=True)
    waitress.serve(app, **kwarg)

def exception_report(exc):
    """generate exception traceback in HTML form"""
    exc_type, exc_value, exc_trace = sys.exc_info()
    head = ["<h2>Internal error</h2>",
            "<p>Traceback (most recent call last:</p>"]
    body = ["<p>{0}</p>".format(l.replace("\n", "<br/>"))
              for l in traceback.format_tb(exc_trace)]
    tail = ["<p><em>{0}: {1}</em></p>".format(exc_type.__name__, exc_value)]
    return ''.join(head+body+tail)

def render_html(node):
    """render HTML node, with exception handling"""
    try:
        # logger.debug('render node: '+print_doc(node))
        result = render(node)
    except Exception as e:
        result = exception_report(e)
    return result

class PrefixRouter:
    """A WSGI application to dispatch on the prefix of the first component of PATH_INFO."""
    def __init__(self):
        self._app = {}
        self._default = None

    def add(self, prefix, app):
        if prefix in self._app:
            raise Error('An application is already registered for prefix '+prefix)
        else:
            self._app[prefix] = app

    def default(self, app):
        if self._default == None:
            self._default = app
        else:
            raise Error('A default application is already registered ')

    def __call__(self, environ, start_response):
        request = Request(environ)
        req_path = request.path_info
        req_method = request.params.get('_method', request.method).upper()
        app = self._default
        for prefix in self._app:
            if req_path.startswith(prefix):
                app = self._app[prefix]
                break
        if app == None:
            return not_found(environ, start_response, message='Nothing found for '+request.path_qs)
        else:
            request.path_info = req_path.replace(prefix, '', 1)
            try:
                cname = app.__class__.__name__
                response = request.get_response(app)
                logger.debug('{0}: {1} {2} -> {3}'.format(cname, req_method, request.path_qs, response.status))
            except Exception as e:
                response = Response()
                response.text = exception_report(e)
            return response(environ, start_response)

# Rendering modes
UNKNOWN_MODE   = 0
HTML_FULL_MODE = 1
HTML_PART_MODE = 2
XML_MODE       = 3
JSON_MODE      = 4

class PatternRouter:
    """A WSGI application to dispatch on the first component of PATH_INFO using patterns.
       This application uses the action map to map a regular expression to a callable.
       It then invokes this callable, which is expected to return a list of nodes that contain
       a renderable representation of the content to be delivered.

       Render mode   full  partial  template
       -------------------------------------
       HTML full       x      -         x
       HTML part       -      x         x
       XML             -      x         x
       JSON            -      x         -
       """

    def __init__(self):
        self.app = {}
        self.length = {}

    def __call__(self, environ, start_response):
        # TODO: reset hooks (e.g. JS support for delete buttons and HTML textarea)
        # reset_page_top(); reset_page_bottom()
        # interpret request
        request = Request(environ)
        req_method = request.params.get('_method', request.method).upper()
        req_path = request.path_info
        if request.headers.get('X-Requested-With', '') == 'XMLHttpRequest': # jQuery.ajax()
            if   'application/json' in request.accept: render_mode = JSON_MODE
            elif 'text/html'        in request.accept: render_mode = HTML_PART_MODE
            else:                                      render_mode = UNKNOWN_MODE
        else:
            render_mode = HTML_FULL_MODE
        # find first action that matches request
        matching_action = None
        for regex, method, action in action_map:
            match = regex.match(req_path)
            if req_method == method and match: # action found -> exit loop
                matching_action = action
                break
        response = Response(content_type='text/html', status=200)
        # run action or send error report
        if matching_action: # run action with request object and match arguments
            try:
                logger.debug('{0} {1}'.format(method, request.path_qs))
                result = action(request, **match.groupdict())
            except Exception as e:
                result = node('block', '', content=exception_report(e))
                response.status = 500
        else: # no match with the defined actions
            result = node('block', '', content='Nothing found for '+request.path_qs)
            response.status = 404
        # render result, which is either a single node, or a tuple of nodes
        if render_mode == JSON_MODE: # render as JSON
            body = json.dumps(result)
            response.content_type = 'application/json'
        elif render_mode == HTML_PART_MODE: # render as HTML, without embedding
            block_node = node('block', '',
                              children=result if isinstance(result, tuple) else [result])
            body = render_html(block_node)
        elif render_mode == HTML_FULL_MODE: # render as HTML, with embedding
            region_node = node('region', 'main',
                               children=result if isinstance(result, tuple) else [result])
            page_node = node('page', 'normal', children=[region_node]) # TODO: page variants
            hook_page_attachments(page_node) # add extra content
            html_node = node('html', '', children=[page_node])
            hook_page_top(html_node)         # additions to top of page, e.g. title, CSS include
            hook_page_bottom(html_node)      # additions to bottom of page, e.g. JS include
            body = render_html(html_node)
        else: # XML, something else?
            error = node('block', '', content='Error in Accept header '+str(request.accept))
            body = render_html(error)
            response.status = 400
        # encode to UTF8 and return according to WSGI protocol
        response.charset = 'utf-8'
        response.text = body # .encode('utf-8')
        return response(environ, start_response)
