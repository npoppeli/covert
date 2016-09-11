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
from .common import str2int, decode_dict, encode_dict
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
            'action': url_for(view_name, route_name, item), 'method':'POST'}

def delete_button(view_name, route_name, item):
    # TODO: add enabled; add data-prompt (Bootstrap JS)
    return {'label': label_for(route_name), 'icon': icon_for(route_name),
            'action': url_for(view_name, route_name, item), 'method':'DELETE'}


class RenderTree:
    nodes = ['content', 'fields', 'labels', 'buttons', 'feedback', 'cursor']
    def __init__(self, request, model, view_name, route_name):
        self.request = request
        self.model = model
        self.view_name = view_name
        self.route_name = route_name
        self.content = None
        self.labels = {}
        self.fields = []
        self.buttons = []
        self.cursor = None
        self.form = {}
        self.feedback = ''
        self.filter = {}

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
        print("move_cursor: filter {} -> count={}".format(cursor.filter, count))
        cursor.skip = max(0, min(count, cursor.skip+cursor.dir*cursor.limit))
        print("move_cursor: skip={} limit={}".format(cursor.skip, cursor.limit))
        cursor.prev = cursor.skip>0
        cursor.next = cursor.skip+cursor.limit < count
        return self

    def add_item(self, oid):
        item = self.model.lookup(oid)
        self.content = item.display()
        self.fields = item.mfields
        self.labels = dict([(field, item.skeleton[field].label) for field in self.fields])
        # TODO: add icons and any other UI information
        return self

    def add_empty_item(self):
        self.content = [{'item':self.model.empty(), 'buttons':[]}]
        self.fields = self.model.mfields
        self.labels = dict([(field, self.model.skeleton[field].label) for field in self.fields])
        return self

    def add_items(self, buttons, sort):
        items = self.model.find(self.cursor.filter,
                                limit=self.cursor.limit, skip=self.cursor.skip, sort=sort)
        if not items:
            self.feedback += 'Nothing found'
            return self
        item0 = items[0]
        print('add_items: adding {} items'.format(len(items)))
        self.content = []
        self.fields = item0.sfields
        self.labels = dict([(field, item0.skeleton[field].label) for field in self.fields])
        for item in items:
            self.content.append({'item':item.display(),
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

    def add_form_buttons(self, route_name):
        if self.content:
            item = self.content[0]['item']
            self.buttons = [form_button(self.view_name, route_name, item, 'ok'),
                            form_button(self.view_name, route_name, item, 'cancel')]
        return self

    def add_search_button(self, route_name):
        if self.content:
            item = self.content[0]['item']
            self.buttons = [form_button(self.view_name, route_name, item, 'search')]
        return self

    def add_form(self):
        self.form = self.model.convert(self.request.params)
        # TODO: form validation, for insert and update
        # validation = self.model.validate(cursor.query, 'query')
        # if validation['ok']:
        #     print('initial post: valid query')
        #     cursor.feedback = ''
        # else:
        #     print('initial post: invalid query')
        #     cursor.query = {}
        #     cursor.feedback = validation['error']
        return self

    def update_if_ok(self, oid):
        item = self.model.lookup(oid)
        self.content = [{'item':item.display(), 'buttons':[]}]
        if self.request.params['_submit'] == 'ok':
            # update item with converted form contents
            item.update(self.form)
            validation = item.validate(item)
            if validation['ok']:
                result = item.write(validate=False)
                if result['ok']:
                    self.content = [{'item': item.display(), 'buttons': []}]
                else:
                    self.feedback = 'Modified document {} could not be stored'.format(item)
            else:
                self.feedback = 'Modified document {} not valid: {}'.format(item, validation['error'])
        return self

    def insert_if_ok(self):
        if self.request.params['_submit'] == 'ok':
            # create item from converted form contents
            item = self.model(self.form)
            validation = item.validate(item)
            if validation['ok']:
                result = item.write(validate=False)
                if result['ok']:
                    self.content = [{'item': item.display(), 'buttons': []}]
                else:
                    self.feedback = 'New document {} could not be stored'.format(item)
            else:
                self.feedback = 'New document {} not valid: {}'.format(item, validation['error'])
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
        # TODO: delete button requires prompt and JS
        return self.tree.add_item(self.params['id'])\
                        .add_buttons(['index', 'update', 'delete'])\
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
                        .add_search_button('match')\
                        .asdict()

    @route('/search', method='POST', template='index')
    def match(self):
        """show result list of search"""
        # TODO: handle search operators:
        # TODO: $key $op $value, where $op is 'in' for 'text' and 'memo', otherwise 'eq'
        return self.tree.add_cursor('search')\
                        .move_cursor()\
                        .add_items(['show', 'modify', 'delete'], self.sort)\
                        .add_buttons(['new'])\
                        .asdict()

    @route('/{id:objectid}/modify', template='update')
    def modify(self):
        """get form for modify/update action"""
        return self.tree.add_item(self.params['id'])\
                        .add_form_buttons('update')\
                        .asdict()

    @route('/{id:objectid}', method='PUT', template='show;update')
    def update(self): # update person
        # if Cancel clicked: redirect back to referer
        # if OK clicked:
        #   form -> document
        #   if valid:
        #     display document, add feedback 'OK'
        #     style = 0
        #   else:
        #     add form contents back to render tree, add feedback with errors
        #     style = 1
        return self.tree.add_form()\
                        .update_if_ok(self.params['id'])\
                        .asdict()

    @route('/new', template='create')
    def new(self):
        """get form for new/create action"""
        return self.tree.add_empty_item()\
                        .add_form_buttons('create')\
                        .asdict()

    @route('', method='POST', template='show;create')
    def create(self):
        """create new item"""
        return self.tree.add_form()\
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
    #     Import documents from file.
    #     Return value if number of validated documents imported.
    #     """
    #     pass # import documents of this model from CSV file (form-based file upload)
