# -*- coding: utf-8 -*-
"""Classes and functions related to HTTP and WSGI servers.

The switching router creates a response object with full HTML, partial HTML or JSON,
depending on the request parameters.
"""

import html, sys, traceback, waitress
from webob import BaseRequest as Request, Response # performance of BaseRequest is better
from . import setting
from .common import encode_dict
from .report import logger

def http_server(app, **kwarg):
    """HTTP server for development purposes"""
    logger.debug('Starting HTTP server')
    # wrapped = ErrorMiddleware(app, debug=True)
    waitress.serve(app, **kwarg)

def not_found(environ, start_response):
    """Function that can be called by WSGI dispatcher if no URL matches"""
    start_response('404 Not Found', [('Content-Type', 'text/plain')])
    return ['Not Found']

def bad_request(environ, start_response):
    """Function that can be called by WSGI dispatcher if no application
    is available for the type of request
    """
    start_response('400 Not Found', [('Content-Type', 'text/plain')])
    return ['Bad request']

def exception_report(exc, ashtml=True):
    """Generate exception traceback, as plain text or HTML

    Arguments:
        exc    (Exception): exception object
        ashmtl (bool):      render as HTML (True) or plain text (False)

    Returns:
        str: exception report as plain or HTML text
    """
    exc_type, exc_value, exc_trace = sys.exc_info()
    if ashtml:
        head = ["<h2>Internal error</h2>", "<p>Traceback (most recent call last:</p>"]
        body = ["<p>{0}</p>".format(l.replace("\n", "<br/>"))
                for l in traceback.format_tb(exc_trace)]
        tail = ["<div><pre>{0}: {1}</pre></div>".format(exc_type.__name__, html.escape(str(exc_value)))]
    else:
        head = ["Internal error. ", "Traceback (most recent call last:"]
        body = traceback.format_tb(exc_trace)
        tail = ["{0}: {1}".format(exc_type.__name__, str(exc_value))]
    return '\n'.join(head+body+tail)

class SwitchRouter:
    """WSGI application that serves as front-end to one or more web applications.

    This WSGI application checks PATH_INFO and the 'X-Requested-With' request header
    to determine what the operating mode is: static file, complete HTML page, HTML
    fragment, XML document or JSON document. Each operating mode is handled by a
    different WSGI application. These applications should be registered by calling
    static(), page(), fragment(), xml() and json() methods.
    """
    # Operating modes
    STATIC_MODE  = 0 # static file
    PAGE_MODE    = 1 # complete HTML page
    FRAG_MODE    = 2 # HTML fragment
    XML_MODE     = 3 # XML document
    JSON_MODE    = 4 # JSON document
    UNKNOWN_MODE = 5 # unknown

    mode_name = ['STATIC', 'PAGE', 'FRAGMENT', 'XML', 'JSON']

    def __init__(self):
        self._app = {self.STATIC_MODE : bad_request,
                     self.PAGE_MODE   : bad_request,
                     self.FRAG_MODE   : bad_request,
                     self.XML_MODE    : bad_request,
                     self.JSON_MODE   : bad_request,
                     self.UNKNOWN_MODE: bad_request}
        self._static = ''

    def static(self, app, prefix):
        self._app[self.STATIC_MODE] = app
        self._static = prefix

    def page(self, app):
        self._add(self.PAGE_MODE, app)

    def fragment(self, app):
        self._add(self.FRAG_MODE, app)

    def xml(self, app):
        self._add(self.XML_MODE, app)

    def json(self, app):
        self._add(self.JSON_MODE, app)

    def _add(self, mode, app):
        self._app[mode] = app

    def __call__(self, environ, start_response):
        request = Request(environ)
        req_method = request.params.get('_method', request.method).upper()
        if request.path_info.startswith(self._static):
            mode = self.STATIC_MODE
            request.path_info = request.path_info.replace(self._static, '', 1)
        elif request.headers.get('X-Requested-With', '') == 'XMLHttpRequest': # jQuery.ajax()
            if 'application/json' in request.accept:
                mode = self.JSON_MODE
            elif 'text/html' in request.accept:
                mode = self.FRAG_MODE
            else:
                mode = self.UNKNOWN_MODE
        else:
            mode = self.PAGE_MODE
        try:
            if setting.debug:
                print('{0}: {1} {2}'.\
                      format(self.mode_name[mode], req_method, request.path_qs))
            response = request.get_response(self._app[mode])
            if setting.debug:
                print('{0}: status={1} body={2} characters'.\
                      format(self.mode_name[mode], response.status, len(response.body)))
        except Exception as e:
            response = Response()
            response.text = exception_report(e)
            print('{0} exception:', exception_report(e, False))
        return response(environ, start_response)


class MapRouter:
    """WSGI application that dispatches on the first component of PATH_INFO using patterns.

    This application uses a global route map to map a regular expression to a view and a route.
    The route is a method of a view class. The view class is instantiated with two parameters:
    the request object, and the match dict. Then the route method is called, which is expected to
    return a render tree, a dictionary containing the content to be serialized and delivered. The
    render tree is serialized by serialize(). The result of the serialization is processed by
    finalize(). Sub-classes of MapRouter can redefine serialize() and finalize() to achieve
    certain effects.
    """

    def __init__(self):
        self.content_type = 'text/html'

    def serialize(self, result, template):
        return setting.templates[template].render(this=result)

    def finalize(self, result):
        return result

    def __call__(self, environ, start_response):
        controller_name = self.__class__.__name__
        # interpret request
        request = Request(environ)
        req_method = request.params.get('_method', request.method).upper()
        req_path = request.path_info
        # find first route that matches request
        view_cls = None
        for route in setting.routes: # route=(pattern, method, templates, regex, cls, name)
            match = route.regex.match(req_path)
            if route.method == req_method and match: # exit loop if matching route found
                view_cls, route_name, route_templates = route.cls, route.name, route.templates
                break
        response = Response(content_type=self.content_type, status=200)
        # run route or send error report
        if view_cls:
            try:
                view_obj = view_cls(request, match.groupdict(),
                                    setting.models[view_cls.model], route_name)
                route_method = getattr(view_obj, route_name)
                result = route_method()
                template = route_templates[result.get('style', 0)]
                result = self.serialize(result, template)
            except Exception as e:
                result = exception_report(e, ashtml=(self.content_type=='text/html'))
                print('{}: exception occurred in {}'.format(controller_name, route_name))
                if self.content_type != 'text/html':
                    print(result)
                response.status = 500
        else: # no match in the known routes
            print('{}: {} {}'.format(controller_name, 'nothing found for', request.path_qs))
            result = 'Nothing found for '+request.path_qs
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
        """remove empty/blank lines and initial whitespace of the other lines"""
        page = setting.templates[self.template].render(content=result)
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
