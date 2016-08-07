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
from .common import str2int, decode_dict
from . import setting

setting.icons = {
   'show'   : 'fa fa-photo',
   'index'  : 'fa fa-list-alt',
   'search' : 'fa fa-search',
   'match'  : 'fa fa-eye',
   'modify' : 'fa fa-pencil',
   'update' : 'fa fa-pencil',
   'new'    : 'fa fa-new',
   'create' : 'fa fa-new',
   'delete' : 'fa fa-trash-o',
   'home'   : 'fa fa-home',
   'info'   : 'fa fa-info-circle',
   'ok'     : 'fa fa-check',
   'refresh': 'fa fa-refresh',
   'cancel' : 'fa fa-times'
}

def icon_for(name):
#TODO: authorization determines the state (enabled, disabled)
    return setting.icons.get(name, 'fa fa-flash')

setting.labels = {
     'show'   : 'Show|Toon|Show',
     'index'  : 'Index|Index|..',
     'search' : 'Search|Zoek|Sök',
     'match'  : 'Match|Resultaat|Resultat',
     'modify' : 'Modify|Wijzig|Ändra',
     'update' : 'Update|Wijzig|Ändra',
     'new'    : 'New|Nieuw|Ny',
     'create' : 'Create|Creeer|Skapa',
     'delete' : 'Delete|Verwijder|Radera',
     'home'   : 'Home|Begin|Hem',
     'info'   : 'Info|Info|Info',
     'ok'     : 'OK|OK|OK',
     'refresh': 'Refresh|Ververs|Fylla på',
     'cancel' : 'Cancel|Annuleer|Upphäva'
}

def label_for(name):
    return setting.labels.get(name, 'unknown')

def url_for(view, name, item):
    url = setting.patterns[view+'_'+name].format(**item)
    return url

# Cursor: class to represent state of browsing through item collection
class Cursor(dict):
    __slots__ = ('skip', 'limit', 'count', 'incl', 'incl0', 'dir',
                 'query', 'equery', 'submit')
    _numbers  = ('skip', 'limit', 'count', 'incl', 'incl0', 'dir')
    def __init__(self, model, request=None):
        super().__init__()
        self.model = model
        self.skip, self.limit, self.count = 0, 10, 0
        self.incl, self.incl0, self.dir = 0, 0, 0
        if request:
            query = {}
            for key, value in request.params.items():
                if key.startswith('_'):
                    newkey = key[1:]
                    setattr(self, newkey, str2int(value) if newkey in self._numbers else value)
                elif value:
                    query[key] = value
            if self.query == '': # initial post
                valid = self.model.validate(query, 'query')
                if valid['ok']:
                    self.query = query
                    self.error = {}
                else:
                    self.query = {}
                    self.error = valid['error']
            else: # follow-up post
                self.query = decode_dict(self.query)
        else:
            self.query = {}
        # equery = query (user query) + extra criterium depending on 'incl'
        self.equery = {'active':''} if self.incl == 1 else {}
        self.equery.update(self.query)
        if (self.count == 0) or (self.incl != self.incl0): # no count or 'incl' has changed
            self.count = self.model.count(self.equery)
        if request:
            self.skip = max(0, min(self.count, self.skip+self.dir*self.limit))
    # in form template:
    # action, incl (toggle), incl0 (hidden), skip (hidden), count (hidden), limit (menu),
    # query (hidden), prev_on (boolean), next_on (boolean)
    # prev_on = self.skip>0, next_on = self.skip+self.limit<self.count

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

# decorator used for the routes (view methods)
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

# regular expressions used in routes
patterns = {
    'alpha'   : r'[a-zA-Z]+',
    'digits'  : r'\d+',
    'objectid': r'\w{24}'
}

def split_route(pattern):
    return list(chain.from_iterable([p.split('}') for p in pattern.split('{')]))

def route2pattern(pattern):
    parts = split_route(pattern)
    parts[1::2] = list(map(lambda p: '{{{0}}}'.format(p.split(':')[0]), parts[1::2]))
    return ''.join(parts)

def route2regex(pattern):
    def split_lookup(s):
        before, after = s.split(':')
        return before, patterns[after]
    parts = split_route(pattern)
    parts[1::2] = list(map(lambda p: '(?P<{0}>{1})'.format(*split_lookup(p)), parts[1::2]))
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
        view_class.prefix = prefix
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
                    new_route = Route(regex, pattern, method, view_class, name, template)
                    setting.patterns[prefix+'_'+name] = pattern
                    setting.routes.append(new_route)
    # sorting in reverse alphabetical order ensures words like 'match' and 'index'
    # are not absorbed by {id} or other components of the regex patterns
    setting.routes.sort(key=lambda r: r.pattern, reverse=True)

def store_result(item):
    return item.write()

def form2doc(req):
    return req.params

def form2update(req):
    return req.params

def form2query(req):
    return req.params

# example: normal_button('person', 'modify', item)
def normal_button(view_name, route_name, item):
    # TODO: add enabled; add data-confirm and data-prompt (Bootstrap JS)
    return {'label': label_for(route_name), 'icon': icon_for(route_name),
            'action': url_for(view_name, route_name, item), 'method':'GET'}

def form_button(view_name, route_name, item):
    return {'label': label_for(route_name), 'icon': icon_for(route_name),
            'action': url_for(view_name, route_name, item), 'method':'POST'}

def delete_button(view_name, route_name, item):
    # TODO: add enabled; add data-confirm and data-prompt (Bootstrap JS)
    return {'label': label_for(route_name), 'icon': icon_for(route_name),
            'action': url_for(view_name, route_name, item), 'method':'DELETE'}

def display_item(item):
    fields = item.mfields
    labels = dict([(field, item.skeleton[field].label) for field in fields])
    # add fields and labels TODO: add icons and any other UI information
    return {'item':item.display(), 'fields':fields, 'labels':labels}

def display_itemlist(itemlist):
    if itemlist:
        item0 = itemlist[0]
        fields = item0.sfields
        labels = dict([(field, item0.skeleton[field].label) for field in fields])
        # add fields and labels TODO: add icons and any other UI information
        return {'item': item.display(), 'fields':fields, 'labels':labels}
    else:
        return {'itemlist':[], 'fields':[], 'labels':{}}


class BareItemView:
    """
    BareItemView: bare view that does not define routes. It serves as superclass for
    ItemView and for view classes that define their own specific routes.
    """
    model = 'BareItem'
    prefix = ''
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
        r2 = display_item(r1)
        buttons = [normal_button(self.prefix, 'index',  r1),
                   normal_button(self.prefix, 'update', r1),
                   normal_button(self.prefix, 'delete', r1)]
        # TODO: delete button requires prompt and JS
        return {'item':r2, 'buttons': buttons}

    @route('/index', template='index')
    def index(self):
        """display multiple items (collection)"""
        r1 = self.model.find({}, limit=10, skip=0)
        if not r1:
            return {'feedback':'Nothing found', 'itemlist':[]}
        item0 = r1[0]
        itemlist = []
        fields = item0.sfields
        for item in r1:
            buttons = [normal_button(self.prefix, 'modify', item),
                       normal_button(self.prefix, 'delete', item)]
            # TODO: delete button requires prompt and JS
            itemlist.append({'item':item.display(), 'buttons':buttons})
            # TODO: change field 0 into tuple (label, url)
            # where url=url_for(self.prefix, 'show',   item)
        buttons = [normal_button('new',  url_for(self.prefix, 'new',  r1[0]))]
        result = {'itemlist': r1, 'buttons': buttons}
        return result

    @route('/search', template='search')
    def search(self):
        """create search form"""
        r1 = self.model.empty()
        buttons = {'search':  normal_button('search',  url_for(self.prefix, 'search',  r1))}
        return {'item':r1, 'buttons': buttons}

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
        # buttons per item: show item, modify, update item, delete item
        return r2

    @route('/{id:objectid}/modify', template='modify')
    def modify(self):
        """get form for modify/update action"""
        item_id = self.matchdict['id']
        r1 = self.model.lookup(item_id)
        r2 = r1.display()
        buttons = {'ok':     form_button('ok',     url_for(self.prefix, 'update',  self)),
                   'cancel': form_button('cancel', url_for(self.prefix, 'update', self))}
        return {'item':r2, 'buttons': buttons}

    @route('/{id:objectid}', method='PUT', template='update')
    def update(self): # update person
        # TODO: update if 'OK' was clicked, else use unmodified item
        r1 = self.model.update({'id':self.matchdict['id']}, form2update(self.request))
        r2 = store_result(r1)
        return r2

    @route('/new', template='new')
    def new(self):
        """get form for new/create action"""
        r1 = self.model.empty()
        buttons = {'ok':     form_button('ok',     url_for(self.prefix, 'create',  self)),
                   'cancel': form_button('cancel', url_for(self.prefix, 'create', self))}
        return {'item':r1, 'buttons': buttons}

    @route('', method='POST', template='create')
    def create(self):
        """create new item"""
        # TODO: create if 'OK' was clicked, else do nothing
        r1 = self.model.insert(form2doc(self.request))
        r2 = store_result(r1)
        return r2

    @route('/{id:objectid}', method='DELETE', template='delete')
    def delete(self):
        """delete one item"""
        r1 = self.set_field(self.matchdict['id'], 'active', False) # item.remove() only during clean-up
        # TODO: result page is feedback plus button to /item/index
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
