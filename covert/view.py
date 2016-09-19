# -*- coding: utf-8 -*-
"""
covert.view
-----
Objects and functions related to view(s).
In the present implementation, form validation is performed on the server. In a future version
it could be delegated to the client, using Parsley.js (jQuery) for example.
"""

import re
from inspect import getmembers, isclass, isfunction
from itertools import chain
from .common import str2int, Error
from .common import decode_dict, encode_dict, show_dict
from .model import prune, unflatten
from . import setting

setting.icons = {
   'show'   : 'fa fa-photo',
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
    __slots__ = ['skip', 'limit', 'incl', 'incl0', 'dir', 'filter', 'query', 'prev', 'next', 'action']
    default = {'skip':0, 'limit':10, 'incl':0, 'incl0':0, 'dir':0}

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
            if setting.debug:
                print('follow-up post: decode saved query')
            self.query = decode_dict(self.query)

    def asdict(self):
        self.query = encode_dict(self.query)
        return dict([(key, getattr(self, key)) for key in self.__slots__])

def store_result(item):
    return item.write()

def normal_button(view_name, route_name, item):
    # TODO: add 'enabled' attribute
    return {'label': label_for(route_name), 'icon': icon_for(route_name),
            'action': url_for(view_name, route_name, item), 'method':'GET'}

def form_button(view_name, route_name, item, button_name):
    return {'label': label_for(button_name), 'icon': icon_for(button_name),
            'name': button_name, 'method':'POST',
            'action': url_for(view_name, route_name, item)}

# TODO: delete button requires prompt and JS
def delete_button(view_name, route_name, item):
    # TODO: add enabled; add data-prompt (Bootstrap JS)
    return {'label': label_for(route_name), 'icon': icon_for(route_name),
            'action': url_for(view_name, route_name, item), 'method':'DELETE'}

class RenderTree:
    # elements listed here are included by RenderTree.asdict()
    nodes = ['buttons', 'content', 'controls', 'cursor', 'feedback',
             'fields', 'labels', 'method', 'style']
    def __init__(self, request, model, view_name, route_name):
        self.request = request
        self.model = model
        self.view_name = view_name
        self.route_name = route_name
        self.form = None
        # content of render tree
        self.buttons = []
        self.content = None
        self.controls = {}
        self.cursor = None
        self.feedback = ''
        self.fields = []
        self.labels = {}
        self.method = ''
        self.style = 0

    def add_cursor(self, route_name):
        self.cursor = Cursor(self.request)
        self.cursor.action = url_for(self.view_name, route_name, {})
        return self

    def move_cursor(self):
        cursor = self.cursor
        # filter = user query + condition depending on 'incl'
        cursor.filter = {'active': ''} if cursor.incl == 1 else {}
        cursor.filter.update(cursor.query)
        count = self.model.count(cursor.filter)
        if setting.debug:
            print("move_cursor: filter {} -> count={}".format(cursor.filter, count))
        cursor.skip = max(0, min(count, cursor.skip+cursor.dir*cursor.limit))
        if setting.debug:
            print("move_cursor: skip={} limit={}".format(cursor.skip, cursor.limit))
        cursor.prev = cursor.skip>0
        cursor.next = cursor.skip+cursor.limit < count
        return self

    def add_item(self, oid_or_item, form=False):
        if isinstance(oid_or_item, str):
            item = self.model.lookup(oid_or_item)
        else:
            item = oid_or_item
        for key in item.fields:
            print('{}: {}'.format(key, item[key]))
        flattened = prune(item.display().flatten(), 1)
        for key in flattened.keys():
            print('{}: {}'.format(key, flattened[key]))
        self.content = prune(item.display().flatten(), 0)
        skeleton = item.skeleton
        fields = [f for f in item.fields if skeleton[f].atomic and not
                  (skeleton[f].hidden or (not form and skeleton[f].auto) or
                   skeleton[f].schema in ('text', 'memo'))]
        labels = {}
        for key in fields:
            # TODO: ADD code for multiple field
            prefix = key if key.count('.') == 0 else key[:key.find('.')]
            labels[key] = '' if skeleton[key].auto else skeleton[prefix].label
        self.labels = labels
        self.fields = fields
        return self

    def add_empty_item(self):
        item = self.model.empty() # difference with add_item
        self.content = prune(item.flatten(), 0)
        skeleton = item.skeleton
        fields = [f for f in item.fields if skeleton[f].atomic and not
                  (skeleton[f].hidden or # difference with add_item
                   skeleton[f].schema in ('text', 'memo'))]
        labels = {}
        for key in fields:
            # TODO: ADD code for multiple field
            prefix = key if key.count('.') == 0 else key[:key.find('.')]
            labels[key] = '' if skeleton[key].auto else skeleton[prefix].label
        self.labels = labels
        self.fields = fields
        return self

    def add_form_controls(self):
        controls = {}
        for key in self.labels.keys():
            prefix = key if key.count('.') == 0 else key[:key.find('.')]
            if self.labels[prefix] == '': # hidden fields have empty label
                controls[prefix] = {'type':'hidden', 'control':'input'}
            else:
                controls[prefix] = self.model.fmap[prefix]
        self.controls = controls
        return self

    def add_items(self, buttons, sort):
        items = self.model.find(self.cursor.filter,
                                limit=self.cursor.limit, skip=self.cursor.skip, sort=sort)
        if not items:
            self.feedback += 'Nothing found'
            return self
        item0 = items[0]
        skeleton = item0.skeleton
        fields = [f for f in item0.fields if skeleton[f].atomic and not
                  (skeleton[f].hidden or skeleton[f].multiple or
                   skeleton[f].schema in ('text', 'memo'))]
        labels = {}
        for key in fields:
            prefix = key if key.count('.') == 0 else key[:key.find('.')]
            labels[key] = '' if skeleton[key].auto else skeleton[prefix].label
        self.labels = labels
        self.fields = fields
        self.content = []
        for item in items:
            self.content.append({'item':prune(item.display().flatten(), 0),
                                 'buttons':[normal_button(self.view_name, button, item)
                                            for button in buttons]})
        return self

    def add_show_link(self, field):
        for el in self.content:
            el['item'][field] = (el['item'][field], url_for(self.view_name, 'show', el['item']))
        return self

    def add_buttons(self, buttons):
        if self.content:
            item = self.content[0]['item'] if isinstance(self.content, list) else self.content
            self.buttons = [normal_button(self.view_name, button, item) for button in buttons]
        return self

    def add_form_buttons(self, route_name, method=None):
        if self.content:
            item = self.content
            self.buttons = [form_button(self.view_name, route_name, item, 'ok')]
            if method: # hide method, e.g. PUT inside the form
                self.method = method
            print('add_form_buttons:', self.buttons)
        return self

    def add_search_button(self, route_name):
        if self.content:
            # item = self.content[0]['item']
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
        """display one item"""
        return self.tree.add_item(self.params['id'])\
                        .add_buttons(['index', 'modify', 'delete'])\
                        .asdict()

    @route('/index', method='GET,POST', template='index')
    def index(self):
        """display multiple items (collection)"""
        return self.tree.add_cursor('index')\
                        .move_cursor()\
                        .add_items(['show', 'modify', 'delete'], self.sort)\
                        .add_buttons(['new'])\
                        .asdict()

    @route('/search', template='search')
    def search(self):
        """create search form"""
        return self.tree.add_empty_item()\
                        .add_form_controls()\
                        .add_search_button('match')\
                        .asdict()

    @route('/search', method='POST', template='index')
    def match(self):
        """show result list of search"""
        # TODO: handle search operators:
        # TODO: {$field $op $value}, where $op is 'cont' for 'text' and 'memo', otherwise 'eq'
        # TODO: engine should translate this to its own API for searches
        return self.tree.add_cursor('search')\
                        .move_cursor()\
                        .add_items(['show', 'modify', 'delete'], self.sort)\
                        .add_buttons(['new'])\
                        .asdict()

    @route('/new', template='create')
    def new(self):
        """get form for new/create action"""
        return self.tree.add_empty_item()\
                        .add_form_controls()\
                        .add_form_buttons('create')\
                        .asdict()

    @route('/{id:objectid}/modify', template='form')
    def modify(self):
        """get form for modify/update action"""
        return self.tree.add_item(self.params['id'])\
                        .add_form_controls()\
                        .add_form_buttons('update', 'PUT')\
                        .asdict()

    def _convert_form(self):
        raw_form = {}
        for key, value in self.request.params.items():
            if not key.startswith('_'):
                raw_form[key] = value
        # print('>> read form: raw form\n{}'.format(raw_form))
        unflattened = unflatten(raw_form)
        # print('>> read_form: unflattened\n{}'.format(unflattened))
        return self.model.convert(unflattened)

    @route('/{id:objectid}', method='PUT', template='show;form')
    def update(self):
        """update existing item"""
        item = self.model.lookup(self.params['id'])
        # update item with converted form contents
        form = self._convert_form()
        item.update(form)
        print('>> update: item updated with form contents\n{}'.format(show_dict(item)))
        validation = item.validate(item)
        if validation['ok']:
            result = item.write(validate=False)
            print('>> update: modified item written to db')
            if result['ok']:
                return self.tree.add_item(self.params['id']) \
                    .add_buttons(['index', 'update', 'delete']) \
                    .asdict()
                tree.feedback = 'Modified item'
                return tree.add_item(item).add_buttons(['index', 'update', 'delete']).asdict()
            else: # exception, under normal circumstances this should never occur
                raise Error('Modified item {} could not be stored ({})'.\
                            format(item, result['error']))
        else:
            print('>> update: modified item not valid\n'+validation['error'])
            self.tree.style = 1
            self.tree.feedback = 'Modified item {} not valid: {}'.format(item, validation['error'])
            return self.tree.add_item(self.tree.form)\
                       .add_form_controls() \
                       .add_form_buttons('update', 'PUT')\
                       .asdict()


    def insert_if_ok(self):
        item = self.model.empty
        # update empty item with converted form contents
        item.update(self.form)
        validation = item.validate(item)
        if validation['ok']:
            print('>> update_if_ok: new item written to db')
            result = item.write(validate=False, debug=True)
            if result['ok']:
                self.content = [{'item': item.display(), 'buttons': []}]
            else: # exception, under normal circumstances this should never occur
                raise Error('New item {} could not be stored'.format(item))
        else:
            self.feedback = 'New item {} not valid: {}'.format(item, validation['error'])
        return self

    @route('', method='POST', template='show;form')
    def create(self):
        """create new item"""
        return self.tree.read_form()\
                        .insert_if_ok()\
                        .asdict()

    @route('/{id:objectid}', method='DELETE', template='delete')
    def delete(self):
        """delete one item functionally, i.e. mark as inactive
        item.remove() is only used for permanent removal, i.e. clean-up"""
        oid = self.params['id']
        r1 = self.set_field(oid, 'active', False)
        if r1['ok']:
            return {'feedback': 'item {} set to inactive'.format(oid),
                    'buttons':[normal_button(self.prefix, 'index', {})]}
        else:
            return {'feedback': 'item {} not modified'.format(oid),
                    'buttons': [normal_button(self.prefix, 'index', {})]}

    #TODO import: import one or more items
    # @route('GET,POST', '/import')
    # def import(cls, filename):
    #     """
    #     import(self, filename): n
    #     Import items from file.
    #     Return value if number of validated items imported.
    #     """
    #     pass # import items of this model from CSV file (form-based file upload)
