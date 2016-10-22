# -*- coding: utf-8 -*-
"""
covert.view
-----
Objects and functions related to view(s).
In the present implementation, form validation is performed on the server. In a future version
it could be delegated to the client, using Parsley.js (jQuery) for example.
"""

import re
from collections import OrderedDict
from inspect import getmembers, isclass, isfunction
from itertools import chain
from .common import InternalError, SUCCESS
from .common import decode_dict, encode_dict
from .model import unflatten, mapdoc
from . import setting

def str2int(s):
    """convert str to integer, or otherwise 0"""
    try:
        number = int(s)
    except:
        number = 0
    return number

setting.icons = {
   'show'   : 'fa fa-eye',
   'index'  : 'fa fa-list-alt',
   'search' : 'fa fa-search',
   'match'  : 'fa fa-search',
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

class Route:
    def __init__(self, pattern, method, templates, regex, cls, name):
        self.pattern = pattern
        self.method = method
        self.templates = templates
        self.cls = cls
        self.name = name
        self.regex = regex

    def __str__(self):
        return("{0} {1} -> {2}:{3}, templates={4}".
               format(self.pattern, self.method, self.cls.__name__, self.name,
                      ', '.join(self.templates)))

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
    for class_name, view_class in getmembers(module, isclass):
        if (class_name in ['BareItemView', 'ItemView'] or
            not issubclass(view_class, BareItemView) or
            not (len(class_name) > 4 and class_name.endswith('View'))):
            continue
        view_name = class_name.replace('View', '', 1).lower()
        view_class.view_name = view_name
        for member_name, member in getmembers(view_class, isfunction):
            if hasattr(member, 'pattern'): # current member (method) is a route
                full_pattern  = '/' + view_name + member.pattern
                pattern       = route2pattern(full_pattern)
                regex         = route2regex(full_pattern)
                templates     = [] # each route can have 1 or more templates
                for name in member.template.split(';'):
                    template_name = view_name+'_' + name
                    parent_name   = 'item_'       + name
                    if template_name in setting.templates:
                        templates.append(template_name)
                    elif parent_name in setting.templates:
                        templates.append(parent_name)
                    else:
                        templates.append('default')
                for method in member.method.split(','):
                    setting.patterns[view_name+'_'+member_name] = pattern
                    setting.routes.append(Route(pattern, method, templates,
                                                re.compile(regex), view_class, member_name))
    # sorting in reverse alphabetical order ensures words like 'match' and 'index'
    # are not absorbed by {id} or other components of the regex patterns
    setting.routes.sort(key=lambda r: r.pattern, reverse=True)

class Cursor:
    __slots__ = ['skip', 'limit', 'incl', 'incl0', 'dir',
                 'filter', 'query', 'prev', 'next', 'action', 'submit']
    default = {'skip':0, 'limit':10, 'incl':0, 'incl0':0, 'dir':0, 'submit':''}

    def __init__(self, request):
        initial = '_incl' not in request.params.keys()
        for key, value in self.default.items():
            setattr(self, key, value)
        self.query = {}
        self.filter = {}
        query = {}
        for key, value in request.params.items():
            if key.startswith('_'):
                setattr(self, key[1:], str2int(value) if key[1:] in self.default else value)
            elif value:
                query[key] = value
        self.incl0 = self.incl
        if initial: # initial post
            self.query = query
        else: # follow-up post
            self.query = decode_dict(self.query)

    def asdict(self):
        self.query = encode_dict(self.query)
        return dict([(key, getattr(self, key, '')) for key in self.__slots__])

def normal_button(view_name, route_name, item):
    # TODO: add 'enabled' attribute
    return {'label': label_for(route_name), 'icon': icon_for(route_name),
            'action': url_for(view_name, route_name, item), 'method':'GET'}

def form_button(view_name, route_name, item, button_name):
    return {'label': label_for(button_name), 'icon': icon_for(button_name),
            'name': button_name, 'method':'POST',
            'action': url_for(view_name, route_name, item)}

def delete_button(view_name, route_name, item):
    # TODO: add enabled; add data-prompt (Bootstrap JS)
    return {'label': label_for(route_name), 'icon': icon_for(route_name),
            'action': url_for(view_name, route_name, item), 'method':'DELETE'}

class RenderTree:
    # elements listed here are included by RenderTree.asdict()
    nodes = ['buttons', 'cursor', 'data', 'message', 'meta', 'method', 'status', 'style']
    def __init__(self, request, model, view_name, route_name):
        self.request = request
        self.model = model
        self.view_name = view_name
        self.route_name = route_name
        self.form = None
        # content of render tree
        self.buttons = []
        self.cursor = None
        self.data = None
        self.message = ''
        self.meta = None
        self.method = ''
        self.status = '' # success, fail, error
        self.style = 0

    def add_cursor(self, route_name):
        self.cursor = Cursor(self.request)
        self.cursor.action = url_for(self.view_name, route_name, {})
        return self

    def transform_query(self):
        r1 = self.cursor.query
        # print('>> transform_query: cursor.query={}'.format(r1))
        r2 = unflatten(r1)
        # print('>> transform_query: unflattened ={}'.format(r2))
        r3 = mapdoc(self.model.qmap, r2)
        # print('>> transform_query: qmapped     ={}'.format(r3))
        self.cursor.query = r3
        return self

    def move_cursor(self):
        cursor = self.cursor
        # filter = user query + condition depending on 'incl'
        cursor.filter = {} if cursor.incl == 1 else {'active':('==', True)}
        cursor.filter.update(cursor.query)
        count = self.model.count(cursor.filter)
        # print('>> move_cursor: {} items with filter={}'.format(count, cursor.filter))
        cursor.skip = max(0, min(count, cursor.skip+cursor.dir*cursor.limit))
        cursor.prev = cursor.skip>0
        cursor.next = cursor.skip+cursor.limit < count
        return self

    def add_item(self, oid_or_item):
        if isinstance(oid_or_item, str):
            item = self.model.lookup(oid_or_item)
        else:
            item = oid_or_item
        self.data = item
        # TODO: add boolean vector 'active' to the render tree
        return self

    def add_empty_item(self):
        self.data = self.model.empty()
        return self

    def add_items(self, buttons, sort):
        items = self.model.find(self.cursor.filter,
                                limit=self.cursor.limit, skip=self.cursor.skip, sort=sort)
        self.data = []
        if not items:
            self.message += 'Nothing found for query {}'.format(self.cursor.query)
            return self
        for item in items:
            self.data.append({'item':item,
                              'buttons':[normal_button(self.view_name, b, item) for b in buttons]})
        # TODO: add boolean vector 'active' to the render tree
        return self

    def flatten_item(self):
        self.data = self.data.display().flatten()
        return self

    def flatten_items(self):
        for row in self.data:
            row['item'] = row['item'].display().flatten()
        return self

    def prune_item(self, depth, erase=False, form=False):
        item_meta = self.model.meta
        meta, item = OrderedDict(), OrderedDict()
        for key, value in self.data.items():
            path = key.split('.')
            field = path[-2] if path[-1].isnumeric() else path[-1]
            field_meta = item_meta[field]
            if (key.count('.') < depth) and not\
                    (field_meta.schema=='itemref' and form):
                item[key] = '' if erase else value
                meta[key] = {'label'   : field_meta.label,
                             'enum'    : field_meta.enum,
                             'formtype': 'hidden' if field_meta.auto else field_meta.formtype,
                             'auto'    : field_meta.auto,
                             'control' : field_meta.control}
        self.data, self.meta = item, meta
        return self

    def prune_items(self, depth):
        item_meta = self.model.meta
        meta, ready = OrderedDict(), False
        for row in self.data:
            item = OrderedDict()
            for key, value in row['item'].items():
                path = key.split('.')
                field = path[-2] if path[-1].isnumeric() else path[-1]
                field_meta = item_meta[field]
                if (key.count('.') < depth) and not\
                        (field_meta.multiple or field_meta.auto or\
                         field_meta.schema in ('text', 'memo', 'itemref')):
                    item[key] = value
                    if not ready:
                        meta[key] = {'label'   : field_meta.label,
                                     'formtype': field_meta.formtype,
                                     'control' : field_meta.control}
            row['item'] = item
            self.meta, ready = meta, True
        return self

    def add_buttons(self, buttons):
        if self.data:
            item = self.data[0]['item'] if isinstance(self.data, list) else self.data
            self.buttons = [(delete_button if button == 'delete' else
                             normal_button)(self.view_name, button, item) for button in buttons]
        return self

    def add_form_buttons(self, route_name, method=None):
        if self.data:
            item = self.data
            self.buttons = [form_button(self.view_name, route_name, item, 'ok')]
            if method: # hide method (e.g. PUT) inside the form
                self.method = method
        return self

    def add_search_button(self, route_name):
        if self.data:
            # item = self.data[0]['item']
            self.buttons = [form_button(self.view_name, route_name, {}, 'search')]
        return self

    def asdict(self):
        if self.cursor:
            self.cursor = self.cursor.asdict()
        return dict([(key, getattr(self, key)) for key in self.nodes])


class BareItemView:
    """
    BareItemView: bare view that does not define routes. It serves as superclass for
    ItemView and for view classes that define their own specific routes.
    """
    model = 'BareItem'
    view_name = ''
    def __init__(self, request, matches, model, route_name):
        self.request = request
        self.params = matches
        self.model = model
        self.tree = RenderTree(request, model, self.view_name, route_name)


class ItemView(BareItemView):
    """
    ItemView: superclass for views that implement the Atom Publishing protocol
    (create, index, new, update, delete, edit, show) plus extensions.
    """
    model = 'Item'
    sort = [] # TODO: (1) should not depend on db engine; (2) passing to render tree methods is awkward

    @route('/{id:objectid}', template='show')
    def show(self):
        """show one item"""
        # TODO: delete button is enabled iff item.active
        return self.tree.add_item(self.params['id'])\
                        .add_buttons(['index', 'search', 'modify', 'delete'])\
                        .flatten_item()\
                        .prune_item(2)\
                        .asdict()

    @route('/index', method='GET,POST', template='index')
    def index(self):
        """show multiple items (collection)"""
        # TODO: delete button is enabled iff item.active
        return self.tree.add_cursor('index')\
                        .move_cursor()\
                        .add_items(['show', 'modify', 'delete'], self.sort)\
                        .add_buttons(['new'])\
                        .flatten_items()\
                        .prune_items(1)\
                        .asdict()

    @route('/search', template='form')
    def search(self):
        """make a search form. Tip for later: Mirage (JS Gmeta for search queries)"""
        return self.tree.add_empty_item()\
                        .add_search_button('match')\
                        .flatten_item()\
                        .prune_item(1, erase=True, form=True)\
                        .asdict()

    @route('/search', method='POST', template='index')
    def match(self):
        """show the result list of a search"""
        return self.tree.add_cursor('search')\
                        .transform_query()\
                        .move_cursor()\
                        .add_items(['show', 'modify', 'delete'], self.sort)\
                        .add_buttons(['new'])\
                        .flatten_items()\
                        .prune_items(1)\
                        .asdict()

    @route('/new', template='form')
    def new(self):
        """make a form for new/create action"""
        return self.tree.add_empty_item()\
                        .add_form_buttons('create')\
                        .flatten_item()\
                        .prune_item(2, erase=True, form=True)\
                        .asdict()

    @route('/{id:objectid}/modify', template='form')
    def modify(self):
        """make a form for modify/update action"""
        return self.tree.add_item(self.params['id'])\
                        .add_form_buttons('update', 'PUT')\
                        .flatten_item()\
                        .prune_item(2, form=True)\
                        .asdict()

    def _convert_form(self):
        raw_form = {}
        for key, value in self.request.params.items():
            if not key.startswith('_'):
                raw_form[key] = value
        return self.model.convert(unflatten(raw_form))

    @route('/{id:objectid}', method='PUT', template='show;form')
    def update(self):
        """update an existing item"""
        # fetch item from database and update with converted form contents
        item = self.model.lookup(self.params['id'])
        form = self._convert_form()
        item.update(form)
        validation = item.validate(item)
        if validation['ok']:
            result = item.write(validate=False)
            if result['status'] == SUCCESS:
                tree = self.tree
                tree.message = 'Modified item {}'.format(str(item))
                return tree.add_item(item) \
                           .add_buttons(['index', 'update', 'delete']) \
                           .flatten_item() \
                           .prune_item(2) \
                           .asdict()
            else: # exception, under normal circumstances this should never occur
                raise InternalError('Modified item {} could not be stored ({})'.\
                            format(str(item), result['error']))
        else:
            tree = self.tree
            tree.style = 1
            tree.message = 'Modified item {} has validation errors {}'.\
                            format(str(item), validation['error'])
            return tree.add_item(item)\
                       .add_form_buttons('update', 'PUT')\
                       .flatten_item()\
                       .prune_item(2, form=True)\
                       .asdict()

    @route('', method='POST', template='show;form')
    def create(self):
        """create a new item"""
        # fetch item from database and update with converted form contents
        item = self.model.empty()
        form = self._convert_form()
        item.update(form)
        validation = item.validate(item)
        #print('>> create: new item=')
        #for key, value in item.items():
        #    print("{:<10}: {}".format(key, value))
        if validation['ok']:
            result = item.write(validate=False)
            if result['ok']:
                tree = self.tree
                tree.message = 'New item {}'.format(str(item))
                return tree.add_item(item) \
                           .add_buttons(['index', 'update', 'delete']) \
                           .flatten_item() \
                           .prune_item(2) \
                           .asdict()
            else: # exception, under normal circumstances this should never occur
                raise InternalError('New item {} could not be stored ({})'.\
                            format(str(item), result['error']))
        else:
            tree = self.tree
            tree.style = 1
            tree.message = 'New item {} has validation errors {}'.\
                            format(str(item), validation['error'])
            return tree.add_item(item)\
                       .add_form_buttons('update', 'PUT')\
                       .flatten_item()\
                       .prune_item(2, form=True, erase=True)\
                       .asdict()

    @route('/{id:objectid}', method='DELETE', template='delete')
    def delete(self):
        """delete one item functionally, i.e. mark as inactive
        item.remove() is only used for permanent removal, i.e. clean-up"""
        item = self.model.lookup(self.params['id'])
        r1 = item.set_field('active', False)
        if r1['ok']:
            return {'status': 'success',
                    'message': 'item {} set to inactive'.format(str(item))}
        else:
            return {'status': 'failure',
                    'message': 'item {} not modified'.format(str(item))}

    #TODO import: import one or more items
    # @route('GET,POST', '/import')
    # def import(cls, filename):
    #     """
    #     import(self, filename): n
    #     Import items from file.
    #     Return value if number of validated items imported.
    #     """
    #     pass # import items of this model from CSV file (form-based file upload)
