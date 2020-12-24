# -*- coding: utf-8 -*-
"""Classes and functions related to HTTP and WSGI servers.

The most important items in this module are the two router classes.
The switching router creates a response object with full HTML, partial HTML or JSON,
depending on the request parameters.
The mapping router creates a response object based on route patterns.
"""

import logging, re, waitress
from datetime import datetime
# we use BaseRequest instead of Request because of performance reasons
from webob import BaseRequest as Request, Response
from webob.static import DirectoryApp
from collections import deque
from . import setting
from . import common as c
from .common import encode_dict, exception_report
from .layout import templates_changed, reload_templates
logger = logging.getLogger('covert')

def http_server(app, **kwarg):
    """HTTP server for development purposes"""
    logger.debug(c._('Starting HTTP server'))
    # wrapped = ErrorMiddleware(app, debug=True)
    waitress.serve(app, **kwarg)

def not_found(environ, start_response):
    """Function that can be called by WSGI dispatcher if no URL matches"""
    start_response('404 Not Found', [('Content-Type', 'text/plain')])
    return ['Not Found']

# Auxiliary functions for CondRouter
regex_is_file = re.compile('/\w+\.\w+')
def is_file_request(request):
    return regex_is_file.match(request.path_info)

def is_page_request(request):
    return not request.is_xhr

def is_fragment_request(request):
    return request.is_xhr and 'text/html' in request.accept

def is_json_request(request):
    return request.is_xhr and 'application/json' in request.accept


class CondRouter:
    """WSGI application that serves as front-end to one or more web applications.

    This WSGI application checks various options of the request to determine what the appropriate
    WSGI application is for further processing. The name of this class is taken from the 'cond'
    expression in LISP.

    Possibilities are: attach application to mount point (e.g. static file), complete HTML page,
    HTML fragment, or JSON document. These applications should be registered by calling the
    mount(), page(), fragment(), and json() methods.
    """

    def __init__(self, empty_root=True, index_page=''):
        self.empty_root = empty_root
        self.index_page = index_page
        self.routes = []
        if not empty_root:
            static_app = DirectoryApp(setting.content, index_page=None)
            self.routes.append((is_file_request, 'FILE', static_app))

    def add(self, cond, mode, app):
        self.routes.append((cond, mode, app))

    def mount(self, app, path):
        def condition(request):
            return '/'.join(request.path_info.split('/')[0:2]) == path
        self.add(condition, 'MOUNT', app)

    def page(self, app):
        self.add(is_page_request, 'PAGE', app)

    def fragment(self, app):
        self.add(is_fragment_request, 'FRAGMENT', app)

    def json(self, app):
        self.add(is_json_request, 'JSON', app)

    def __call__(self, environ, start_response):
        request = Request(environ)
        req_method = request.params.get('_method', request.method).upper()
        # path rewrite in case of index page
        if request.path_info == '/' and self.index_page:
            request.path_info = self.index_page
        # check available routes, where each route is a tuple (condition, mode, app).
        # the first match we find is the one we use
        mode, app = '', not_found
        for route in self.routes:
            if route[0](request):
                mode, app = route[1], route[2]
                break
        if mode == 'MOUNT': # remove mount point from path_info
            path_info = request.path_info
            request.path_info = path_info[path_info.find('/', 1):]
        try:
            response = request.get_response(app)
            logger.debug('"{} {}" {} {} {}'.format(request.method, request.path_qs,
                         response.status, response.content_length, mode))
        except Exception as e:
            response = Response()
            response.text = exception_report(e)
            logger.error(c._('{} {} [mode {}] results in exception {}\n').\
                         format(req_method, request.path_qs, mode, exception_report(e, False)))
        return response(environ, start_response)


class MapRouter:
    """WSGI application that dispatches on the first component of PATH_INFO using patterns.

    This application uses a global route map to map a regular expression to a view and a route.
    The route is a method of a view class. The view class is instantiated with two parameters:
    the request object, and the match dict. Then the route method is called, which must return
    a render tree, a dictionary containing the content to be serialized and delivered. The
    render tree is serialized by serialize(). The result of the serialization is processed by
    finalize(). Sub-classes of MapRouter can redefine serialize() and finalize() to achieve
    certain effects.
    """

    def __init__(self):
        self.content_type = 'text/html'
        # TODO: add history handling
        # Keep history inside the router, so that we can perform an internal redirect.
        # External redirects (HTTP "307 Redirect") do not contain the POST parameters.
        self.history = deque(maxlen=5)

    def serialize(self, result, template):
        if setting.debug and templates_changed():
            reload_templates()
        try:
            html =setting.templates[template](result)
            return html
        except Exception as e:
            logger.error(c._('Evaluation of template {} results in exception {}\n').\
                         format(template, exception_report(e, False)))

    def finalize(self, result):
        return result

    def __call__(self, environ, start_response):
        controller_name = self.__class__.__name__
        # interpret request
        request = Request(environ)
        req_method = request.params.get('_method', request.method).upper()
        response = Response(content_type=self.content_type, status=200)
        # primitive CORS support
        if 'origin' in request.headers:
            response.headers['Access-Control-Allow-Origin'] = request.headers['Origin']
        # special treatment for OPTIONS requests
        if req_method == 'OPTIONS':
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'x-requested-with, content-type'
            response.headers['Access-Control-Max-Age'] = '86400'
            return response(environ, start_response)
        # find first route that matches request
        req_path = request.path_info
        view_cls = None
        # route is tuple (pattern, method, templates, regex, cls, name)
        for route in setting.routes:
            match = route.regex.match(req_path)
            # exit loop if matching route found
            if route.method == req_method and match:
                view_cls, route_name, route_templates = route.cls, route.name, route.templates
                break
        # run route or send error report
        if view_cls:
            try:
                view_obj = view_cls(request, match.groupdict(),
                                    setting.models[view_cls.model], route_name)
                route_method = getattr(view_obj, route_name)
                render_tree = route_method()
                template = route_templates[render_tree.get('style', 0)]
                for cookie in render_tree.get('cookies', []):
                    response.set_cookie(cookie.name, value=cookie.value,
                                        path=cookie.path, max_age=cookie.expires)
                result = self.serialize(render_tree, template)
                response.cache_control.max_age = 0
            except Exception as e:
                result = exception_report(e, ashtml=(self.content_type=='text/html'))
                logger.error(c._('{}: exception occurred in {}').format(controller_name, route_name))
                if self.content_type != 'text/html':
                    logger.error(result)
                response.status = 500
        else: # no match in the known routes
            result = c._('{}: nothing found for {} {}').\
                     format(controller_name, req_method, request.path_qs)
            logger.warning(result)
            response.status = 404
        # encode to UTF8 and return according to WSGI protocol
        response.charset = 'utf-8'
        response.text = self.finalize(result)
        return response(environ, start_response)

class PageRouter(MapRouter):
    """"Subclass of MapRouter for rendering complete HTML pages.

    This application wraps the generated result in an HTML page.
    The HTML page is defined by a template that is passed to the constructor method.
    """

    def __init__(self, name):
        """"The 'name' parameter is the name of the template used to render the content to
        HTML. This should be a template for a complete HTML page.
        """
        super().__init__()
        self.content_type = 'text/html'
        self.template = name

    def finalize(self, result):
        """Add finishing touches to the result. This includes whitespace removal."""
        render_tree = {'content': result, 'debug': setting.debug, 'verbose': setting.verbose}
        page = setting.templates[self.template](render_tree)
        lines = [line.lstrip() for line in page.splitlines() if line and not line.isspace()]
        return '\n'.join(lines)

class JSONRouter(MapRouter):
    """"Subclass of MapRouter for generating JSON content.

    This application sets the result type to application/json and returns
    a JSON document with HTML encoding applied where necessary.
    """

    def __init__(self):
        super().__init__()
        self.content_type = 'application/json'

    def serialize(self, result, template):
        return encode_dict(result)
