# -*- coding: utf-8 -*-
"""
covert.view
-----
Objects and functions related to view(s).
In the present implementation, form validation is performed on the server. In a future version
it could be delegated to the client, using Parsley.js (jQuery) for example.
"""

import re
from inspect import getmembers, isclass
from itertools import chain
from . import setting
from .common import show_dict

setting.icons = {
   'show'  : 'fa fa-photo',
   'index' : 'fa fa-list-alt',
   'search': 'fa fa-search',
   'match' : 'fa fa-eye',
   'modify': 'fa fa-pencil',
   'update': 'fa fa-pencil',
   'new'   : 'fa fa-new',
   'create': 'fa fa-new',
   'delete': 'fa fa-trash-o',
   'home'  : 'fa fa-home',
   'info'  : 'fa fa-info-circle',
   'ok'    : 'fa fa-check',
   'cancel': 'fa fa-times'
}
def icon_for(view, route, **kwarg):
#TODO: authorization determines the state (enabled, disabled)
    return setting.icons.get(route, '')

setting.labels = {
     'show':   'Show|Toon|Show',
     'home':   'Home|Begin|Hem',
}
def label_for(view, route, **kwarg):
    return setting.labels.get(route, '')

def url_for(view, route, qs={}, **kwarg):
    url = setting.routes(view+'_'+route, '').format(**kwarg)
    if qs:
        url = url + '?' + '&'.join(['{0}={1}'.format(k, qs[k]) for k in qs])
    return url

# functions for buttons
# #TODO: these should become classes (button factories). Instances are partial functions
# # with URL and other variables as parameters, and can be passed along to grid etcetera.
# def panel_button(view, action, confirm=None, prompt=None, enabled=True, **kwarg):
#     return node('button', 'panel',
#                 icon=icon_for(view, action), label=label_for(view, action),
#                 enabled=enabled, action=url_for(view, action, **kwarg),
#                 confirm=confirm, prompt=prompt)
# def grid_button(view, action, confirm=None, prompt=None, enabled=True, **kwarg):
#     return node('button', 'grid',
#                 icon=icon_for(view, action), label=label_for(view, action)[0],
#                 enabled=enabled, action=url_for(view, action, **kwarg),
#                 confirm=confirm, prompt=prompt)
# def form_button(label, icon):
#     return node('button', 'form',
#                 icon=icon, label=label, enabled=True, name='$submit', value=label)

# # Cursor: class to represent state of search through item collection
# class Cursor(dict):
#     __slots__ = ('skip', 'limit', 'count', 'inin', 'inins', 'dir',
#                  'query', 'bquery', 'equery', 'submit', 'error')
#     _numbers  = ('skip', 'limit', 'count', 'inin', 'inins', 'dir')
#     def __init__(self, model, request=None):
#         self.skip, self.limit, self.count = 0, 10, 0
#         self.inin, self.inins, self.dir = 0, 0, 0
#         if request:
#             query = {}
#             for key, value in request.params.items():
#                 if key.startswith('$'):
#                     newkey = key[1:]
#                     setattr(self, newkey, str2int(value) if newkey in self._numbers else value)
#                 elif value:
#                     query[key] = value
#             if self.query == '': # initial post
#                 valid = self.modelvalidate(query, 'query')
#                 if valid['ok']:
#                     self.query = query
#                     self.error = {}
#                 else:
#                     self.query = {}
#                     self.error = valid['error']
#             else: # follow-up post
#                 self.query = decode_dict(self.query)
#         else:
#             self.query = {}
#         # equery = bquery (base query)+ query (user query)
#         #   - bquery depends on active toggle
#         #   - query is specified in form, or {}
#         self.equery = {'active':'' if self.inin == 1 else True}
#         self.equery.update(self.query)
#         if (self.count == 0) or (self.inin != self.inins): # count absent or toggle has changed
#             self.count = self.modelcount(self.equery)
#         if request:
#             self.skip = max(0, min(self.count, self.skip+self.dir*self.limit))
#     def form(self, action):
#         qs = encode_dict(self.query) if self.query else ''
#         return node('form', 'cursor', action=action, inin=self.inin, inins=self.inin,
#                     skip=self.skip, count=self.count, limit=self.limit, query=qs,
#                     enableprev=(self.skip>0), enablenext=(self.skip+self.limit<self.count))

class Route:
    def __init__(self,regex, pattern, method, cls, name, template):
        self.regex = regex
        self.pattern = pattern
        self.method = method
        self.cls = cls
        self.name = name
        self.template = template

    def __str__(self):
        return("{0} {1} -> {2}:{3}".
               format(self.pattern, self.method, self.cls.__name__, self.name))

# regular expressions used in routes
patterns = {
    'alpha'   : r'[a-zA-Z]+',
    'digits'  : r'\d+',
    'objectid': r'\w{24}'
}

def cut_route(r):
    return list(chain.from_iterable([p.split('}') for p in r.split('{')]))

def route2pattern(r):
    parts = cut_route(r)
    parts[1::2] = list(map(lambda s: '{{{0}}}'.format(s.split(':')[0]), parts[1::2]))
    return ''.join(parts)

def route2regex(r):
    def split_lookup(s):
        before, after = s.split(':')
        return before, patterns[after]
    parts = cut_route(r)
    parts[1::2] = list(map(lambda s: '(?P<{0}>{1})'.format(*split_lookup(s)), parts[1::2]))
    parts.insert(0, '^')
    parts.append('$')
    return ''.join(parts)

def read_views(module):
    for view_name, view_class in getmembers(module, isclass):
        if view_name in ['BareItemView', 'ItemView'] or not issubclass(view_class, BareItemView):
            continue
        # view classes must have a name that ends in 'View'
        assert len(view_name) > 4 and view_name.endswith('View')
        prefix = view_name.replace('View', '', 1).lower()
        for name in dir(view_class):
            member = getattr(view_class, name)
            if hasattr(member, 'pattern'): # decorated method, i.e. a route
                full_pattern = '/' + prefix + member.pattern
                rx = route2regex(full_pattern)
                regex = re.compile(rx)
                pattern = route2pattern(full_pattern)
                template_name = prefix+'_'+member.template
                if template_name not in setting.templates:
                    template_name = 'default'
                template = setting.templates[template_name]
                for method in member.method.split(','):
                    # print("{} {}: t={} p={}".format(pattern, method, template_name, rx))
                    route = Route(regex, pattern, method, view_class, name, template)
                    setting.routes.append(route)
    # sorting in reverse alphabetical order ensures words like 'match' and 'index'
    # are not absorbed by {id} or other components of the regex patterns
    setting.routes.sort(key=lambda route: route.pattern, reverse=True)

# ItemView class, and decorator used for the routes (view methods)
class route:
    """
    route: decorator for methods in a View class. This adds attributes to methods.
    Once set, these attributes cannot be changed anymore.
    @route(pattern, method, template)
    - pattern: URL pattern, given as a format string
    - method: string identifying HTTP method (e.g. 'GET' or 'GET, POST')
    - template: name of template that renders the result of the view
    """
    def __init__(self, pattern, method='GET', template=''):
        self.pattern  = pattern
        self.method   = method
        self.template = template
    def __call__(self, wrapped):
        wrapped.pattern  = self.pattern
        wrapped.method   = self.method
        wrapped.template = self.template
        return wrapped

def store_result(item):
    return item.write()

def form2doc(req):
    return req.params

def form2update(req):
    return req.params

def form2query(req):
    return req.params

class BareItemView:
    """
    BareItemView: superclass for ItemView and for views with specific routes.
    """
    model = 'BareItem'
    def __init__(self, request, matchdict):
        self.request = request
        self.matchdict = matchdict

class ItemView(BareItemView):
    """
    ItemView: superclass for views that implement the Atom Publishing protocol
    (create, index, new, update, delete, edit, show) plus extensions.
    """
    model = 'Item'

    @route('/{id:objectid}', template='show')
    def show(self):
        """display one item"""
        r1 = self.model.lookup(self.matchdict['id'])
        r2 = r1.display() # use display map of item class
        print('item:', show_dict(r2))
        fields = self.model.sfields
        labels = dict([(field, self.model.skeleton[field].label) for field in fields])
        return {'fields':fields, 'labels':labels, 'item':r2}

    @route('/index', template='index')
    def index(self):
        """display multiple items (collection)"""
        r1 = self.model.find({}, limit=10, skip=0)
        r2 = r1.display()
        return r2

    @route('/search', template='search')
    def search(self):
        """create search form"""
        r1 = self.model.empty()
        return r1 # TODO: action=POST /person/search, buttons = ??, action = url_for(self.name, 'match')

    @route('/search', method='POST', template='match')
    def match(self):
        """show result list of search"""
        query = form2query(self.request)
        r1 = self.model.find(query, limit=10, skip=0)
        r2 = r1.display()
        # cursor = Cursor(self.model, req)
        # if not cursor.query:
        #     logger.debug('match: invalid query '+str(cursor.error))
        #     return self.search(self.request, cursor.error) # show search form and errors
        # #TODO: $key $op $value, where $op is 'in' for 'text' and 'memo', otherwise 'eq'
        return r2

    @route('/{id:objectid}/modify', template='modify')
    def modify(self):
        """get form for modify/update action"""
        item_id = self.matchdict['id']
        r1 = self.model.lookup(item_id)
        # form_action = url_for(self.name, 'update', id=item_id)
        r2 = r1.display()
        return r2 # TODO: action = PUT /person/{id}, buttons = ??

    @route('/{id:objectid}', method='PUT', template='update')
    def update(self): # update person
        r1 = self.model.update({'id':self.matchdict['id']}, form2update(self.request))
        r2 = store_result(r1)
        return r2

    @route('/new', template='new')
    def new(self):
        """get form for new/create action"""
        r1 = self.model.empty()
        # TODO: form_action = url_for(self.name, 'create')
        # TODO: buttons: ok, cancel
        return r1 # TODO: action = POST /person, buttons = ??

    @route('', method='POST', template='create')
    def create(self):
        """create new item"""
        # TODO: if 'OK' was clicked, else use unmodified item
        r1 = self.model.insert(form2doc(self.request))
        r2 = store_result(r1)
        return r2

    @route('/{id:objectid}', method='DELETE', template='delete')
    def delete(self):
        """delete one item"""
        r1 = self.set_field(self.matchdict['id'], 'active', False) # item.remove() only during clean-up
        return r1

    #TODO import: import one or more items
    # @route('GET,POST', '/import')
    # def import(cls, filename):
    #     """
    #     import(self, filename): n
    #     Import documents from file.
    #     Return value if number of validated documents imported.
    #     """
    #     pass # import documents of this model from CSV file (form-based file upload)
