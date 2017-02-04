# -*- coding: utf-8 -*-
"""Objects and functions related to view(s).

Views are classes consisting of route methods and other methods. The route methods
are decorated by '@route'. Each route has a URL pattern, one or more HTTP methods,
and one or more templates.

In the present implementation, form validation is performed on the server. Alternative:
do form validation in the client, using Parsley.js (jQuery) for example.
"""

import re
from collections import OrderedDict
from datetime import datetime, timedelta
from inspect import getmembers, isclass, isfunction
from itertools import chain
from urllib.parse import urlencode
from .common import InternalError, SUCCESS, write_file
from .common import decode_dict, encode_dict, show_dict, show_item3
from .model import unflatten, mapdoc
from . import setting

def str2int(s):
    """Convert str to integer, or otherwise 0."""
    try:
        number = int(s)
    except:
        number = 0
    return number

setting.icons = {
    'show'   :      'fa fa-eye',
    'diagram':      'fa fa-tree',
    'marriage_new': 'fa fa-venus-mars',
    'index'  :      'fa fa-list-alt',
    'search' :      'fa fa-search',
    'match'  :      'fa fa-search',
    'modify' :      'fa fa-pencil',
    'update' :      'fa fa-pencil',
    'new'    :      'fa fa-new',
    'create' :      'fa fa-new',
    'delete' :      'fa fa-trash-o',
    'home'   :      'fa fa-home',
    'info'   :      'fa fa-info-circle',
    'ok'     :      'fa fa-check',
    'refresh':      'fa fa-refresh',
    'cancel' :      'fa fa-times'
}

def icon_for(name):
    """Return icon for route 'name'."""
    return setting.icons.get(name, 'fa fa-flash')

setting.labels = {
     'show'        : 'Show|Toon|Show',
     'diagram'     : 'Tree|Boom|Träd',
     'marriage_new': 'Marriage|Huwelijk|Gifte',
     'index'       : 'Browse|Blader|Bläddra',
     'search'      : 'Search|Zoek|Sök',
     'match'       : 'Match|Resultaat|Resultat',
     'modify'      : 'Modify|Wijzig|Ändra',
     'update'      : 'Update|Wijzig|Ändra',
     'new'         : 'New|Nieuw|Ny',
     'create'      : 'Create|Maak|Skapa',
     'delete'      : 'Delete|Verwijder|Radera',
     'home'        : 'Home|Begin|Hem',
     'info'        : 'Info|Info|Info',
     'ok'          : 'OK|OK|OK',
     'refresh'     : 'Refresh|Ververs|Fylla på',
     'cancel'      : 'Cancel|Annuleer|Upphäva'
}

def label_for(name):
    """Return label for route 'name'."""
    return setting.labels.get(name, 'unknown')

def url_for(view, name, item, query=None):
    """Return URL for route 'name'."""
    url = setting.patterns[view+'_'+name].format(**item)
    if query:
        url += '?' + urlencode(query)
    return url

# Routes
class Route:
    """Route definition.

    The definitions of all routes in all views are stored in the global variable setting.routes.
    """
    def __init__(self, pattern, method, templates, regex, cls, name):
        """Constructor method for Route.

        A Route object consists of (1) attributes that uniquely define the route,
        and (2) attributes that are needed by the controller to call the route.

        Attributes:
            * pattern   (str):   URL pattern
            * method    (str):   HTTP method
            * templates (list):  list of template names (length of list >= 1)
            * regex     (regex): compiled regular expression
            * cls       (class): view class
            * name      (str):   method name
        """
        self.pattern = pattern
        self.method = method
        self.templates = templates
        self.regex = regex
        self.cls = cls
        self.name = name

    def __str__(self):
        return("{0} {1} -> {2}:{3}, templates={4}".
               format(self.pattern, self.method, self.cls.__name__, self.name,
                      ', '.join(self.templates)))

class route:
    """Decorator for methods in a View class.

    This decorator adds attributes to methods. Once set, these attributes cannot be changed anymore.
    """
    def __init__(self, pattern, method='GET', template=''):
        """Constructor for 'route' decorator.

        Attributes:
            * pattern  (str): URL pattern, given as a format string
            * method   (str): string identifying HTTP method (e.g. 'GET' or 'GET, POST')
            * template (str): name(s) of template(s) that render(s) the result of the view
        """
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
    """Split route into components.

    Split route into components: a combined split on '{' and '}' results in a list of lists,
    and chain.from_iterable transforms this into a flat list.
    Routing arguments should have this form: '{name:pattern}', where pattern is one of the keys
    of the 'patterns' dictionary (see above).

    Arguments:
        pattern (str): URL pattern.

    Returns:
        list: components of URL pattern.
    """
    return list(chain.from_iterable([p.split('}') for p in pattern.split('{')]))

def route2pattern(pattern):
    """Create formatting string from route specifier.

    Remove the pattern specifier from all routing arguments in 'pattern', so that
    we get a pattern acceptable to str.format().

    Arguments:
        pattern (str): URL pattern.

    Returns:
        str: string formatting pattern.
    """
    parts = split_route(pattern)
    parts[1::2] = list(map(lambda p: '{{{0}}}'.format(p.split(':')[0]), parts[1::2]))
    return ''.join(parts)

def route2regex(pattern):
    """Create regular expression string from route specifier.

    Translate the patterns in the routing arguments to regular expression notation, so
    that we get a regular expression string.

    Arguments:
        pattern (str): URL pattern.

    Returns:
        str: regular expression string.
    """
    def split_lookup(s):
        before, after = s.split(':')
        return before, patterns[after]
    parts = split_route(pattern)
    parts[1::2] = list(map(lambda p: '(?P<{0}>{1})'.format(*split_lookup(p)), parts[1::2]))
    parts.insert(0, '^')
    parts.append('$')
    return ''.join(parts)

# Views
def read_views(module):
    """Read views from module object.

    Read all views from the module object 'module'. A view is a class that is a sub-class of
    BareItemView and has a name ending in 'View'.
    In each view, locate the members that are of 'function' type and have a 'pattern'
    attribute, indicating they have been decorated with '@route'. These members are
    the routes of the application.

    Arguments:
        module (object): module object.

    Returns:
        None
    """
    for class_name, view_class in getmembers(module, isclass):
        if (class_name in ['BareItemView', 'ItemView'] or
            not issubclass(view_class, BareItemView) or
            not (len(class_name) > 4 and class_name.endswith('View'))):
            continue
        view_name = class_name.replace('View', '', 1).lower()
        view_class.view_name = view_name
        for member_name, member in getmembers(view_class, isfunction):
            if hasattr(member, 'pattern'): # this member (method) is a route
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
    """Representation of the state of browsing through a collection of items.

    A cursor object represent the state of browsing through a collection of items.
    In HTML pages the cursor is represented as a form, with several buttons and toggles.

    For a few attributes, default values are defined in the 'default' dictionary.
    """
    __slots__ = ['skip', 'limit', 'incl', 'dir',
                 'filter', 'query', 'prev', 'next', 'action', 'submit']
    default = {'skip':0, 'limit':10, 'incl':0, 'dir':0, 'submit':''}

    def __init__(self, request, model):
        """Constructor method for Cursor.

        Attributes:
            * skip      (int):     URL pattern
            * limit     (int):     HTTP method
            * incl      (int):     1 if inactive items are included, 0 otherwise
            * dir       (int):     direction of browsing
            * filter    (str):     filter to pass to storage engine
            * query     (str):     transformed dictionary
            * query0    (str):     query dictionary (saved in form)
            * prev      (bool):    True if 'previous' button enabled
            * next      (bool):    True if 'next' button enabled
            * action    (str):     form action
            * submit    (str):     value of the form button that was pressed
        """
        initial = '_skip' not in request.params
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
        if initial: # initial post
            # transform query given by form to actual query
            self.query = mapdoc(model.qmap, unflatten(query))
        else: # follow-up post
            self.query = decode_dict(query)

    def __str__(self):
        d = dict([(key, getattr(self, key, '')) for key in self.__slots__])
        return show_dict(d)

    def asdict(self):
        self.query = encode_dict(self.query)
        return dict([(key, getattr(self, key, '')) for key in self.__slots__])

def normal_button(view_name, action, item):
    """Create render-tree element for normal button."""
    return {'label': label_for(action), 'icon': icon_for(action),
            'action': url_for(view_name, action, item), 'method':'GET'}

def form_button(view_name, action, item, button_name):
    """Create render-tree element for form button."""
    return {'label': label_for(button_name), 'icon': icon_for(button_name),
            'name': button_name,
            'action': url_for(view_name, action, item), 'method':'POST'}

def delete_button(view_name, action, item):
    """Create render-tree element for delete button."""
    return {'label': label_for(action), 'icon': icon_for(action),
            'action': url_for(view_name, action, item), 'method':'DELETE'}

class RenderTree:
    """Tree representation of information created by a route.

    The information that is created by a route (view method) is collected in the render tree.
    This is returned to the controller as a dictionary. The controller serializes this
    dictionary and returns the result to the web client.

    Some elements of the render tree are temporary (needed for the request handling). The other
    attributes are specified by the class attribute 'nodes'. These attributes are used by the
    asdict() method.
    """
    nodes = ['buttons', 'cursor', 'data', 'info',
             'message', 'method', 'status', 'style', 'title']
    def __init__(self, request, model, view_name, action):
        """Constructor method for RenderTree.

        Attributes:
            * request   (Request): HTTP request (WebOb)
            * model     (Item):    model class
            * view_name (str):     name of view class
            * action(str):     name of route (view method)
        """
        # attributes for request handling
        self.request = request
        self.model = model
        self.view_name = view_name
        self.action = action
        # attributes that are used in rendering
        self.buttons = []
        self.cursor = None
        self.data = []
        self.info = {}
        self.message = ''
        self.method = ''
        self.poly = False
        self.status = '' # success, fail, error
        self.style = 0
        self.title = ''

    def add_cursor(self, action):
        """Add cursor object to render tree."""
        self.cursor = Cursor(self.request, self.model)
        self.cursor.action = url_for(self.view_name, action, {})

    def move_cursor(self):
        """Move cursor to new position.

        The actual filter used in the search is built from the search query specified by the user
        in the form, and an extra condition depending on the value of cursor.incl.
        """
        cursor = self.cursor
        cursor.filter = {} if cursor.incl == 1 else {'active': ('==', True)}
        cursor.filter.update(cursor.query)
        count = self.model.count(cursor.filter)
        cursor.skip = max(0, min(count, cursor.skip+cursor.dir*cursor.limit))
        cursor.prev = cursor.skip>0
        cursor.next = cursor.skip+cursor.limit < count

    def add_item(self, oid_or_item, prefix=''):
        """Add item to render tree."""
        if isinstance(oid_or_item, str):
            item = self.model.lookup(oid_or_item)
        else:
            item = oid_or_item
        if self.data:
            self.poly = True
        item['_buttons'] = []
        item['_prefix'] = prefix
        self.data.append(item)
        self.info['active'] = item['active'] # TODO: should work for repeated add_item()
        self.info['recent'] = datetime.now() - item['mtime'] < timedelta(days=7) and item['active']

    def add_items(self, buttons, sort):
        """Add list of items to render tree."""
        self.data, self.poly = [], False
        items = self.model.find(self.cursor.filter,
                                limit=self.cursor.limit, skip=self.cursor.skip, sort=sort)
        if items:
            active, recent = [], []
            delta, now = timedelta(days=31), datetime.now()
            for item in items:
                button_list = [(delete_button if button == 'delete' else
                                normal_button)(self.view_name, button, item) for button in buttons]
                item['_buttons'] = button_list
                item['_prefix'] = ''
                self.data.append(item)
                active.append(item['active'])
                recent.append(now-item['mtime'] < delta and item['active'])
            self.info['active'] = active
            self.info['recent'] = recent
        else:
            qs = ', '.join(["{}{}{}".format(k, v[0], v[1]) for k, v in self.cursor.query.items()])
            self.message += 'Nothing found for query {}'.format(qs)

    def flatten_item(self, nr=0):
        """Flatten one item in the render tree."""
        item = self.data[nr]
        item_meta = item.meta
        ditem = item.display()
        flat_item = ditem.flatten()
        # show_item3('original', 'display', 'flattened', item, ditem, flat_item)
        newitem = OrderedDict()
        for key, value in flat_item.items():
            if key.startswith('_'):
                newitem[key] = value
            else:
                path = key.split('.')
                if path[-1].isnumeric():
                    field = path[-2]
                    field_meta = item_meta[field]
                    pos = int(path[-1])+1
                    label = field_meta.label if pos==1 else str(pos)
                else:
                    field = path[-1]
                    field_meta = item_meta[field]
                    label  = field_meta.label
                proplist = {'label': label, 'enum': field_meta.enum, 'schema': field_meta.schema,
                            'multiple': field_meta.multiple,
                            'formtype': 'hidden' if field_meta.auto else field_meta.formtype,
                            'auto': field_meta.auto, 'control': field_meta.control}
                newitem[key] = {'value':value, 'meta':proplist, 'buttons':[]}
        self.data[nr] = newitem

    def flatten_items(self):
        """Flatten all items in the render tree."""
        for nr in range(len(self.data)):
            self.flatten_item(nr=nr)

    def prune_item(self, nr=0, depth=1, clear=False, form=False, extra=[]):
        """Prune one item in the render tree."""
        item = self.data[nr]
        newitem = OrderedDict()
        for key, field in item.items():
            if key.startswith('_'):
                newitem[key] = field
            elif (key.count('.') < depth) and key not in extra and \
                not (form and field['meta']['schema']=='itemref'):
                if clear: field['value'] = ''
                newitem[key] = field
        self.data[nr] = newitem

    def prune_items(self, depth, extra=[]):
        """Prune all items in the render tree."""
        if self.poly:
            for nr in range(len(self.data)):
                self.prune_item(nr=nr, depth=depth, extra=extra)
        else:
            for nr, item in enumerate(self.data):
                newitem = OrderedDict()
                for key, field in item.items():
                    if key.startswith('_'):
                        newitem[key] = field
                    else:
                        field_meta = field['meta']
                        if (key.count('.') < depth) and key not in extra and not \
                            (field_meta['multiple'] or field_meta['auto'] or
                            field_meta['schema'] in ('text', 'memo', 'itemref')):
                            newitem[key] = field
                self.data[nr] = newitem

    def apply_prefix(self):
        for decorated in self.data:
            prefix = decorated['prefix']
            if prefix:
                item = decorated['item']
                newitem = OrderedDict()
                for key, field in item.items():
                    newitem[prefix+'.'+key] = field
                decorated['item'] = newitem

    def add_buttons(self, buttons):
        """Add buttons (normal and delete) to render tree."""
        if self.data:
            item = self.data[0]
            self.buttons = [(delete_button if button == 'delete' else
                             normal_button)(self.view_name, button, item) for button in buttons]

    def add_form_buttons(self, action, method=None):
        """Add form buttons to render tree."""
        if self.data:
            item = self.data[0]
            self.buttons = [form_button(self.view_name, action, item, 'ok')]
            if method: # hide method (e.g. PUT) inside the form
                self.method = method

    def add_search_button(self, action):
        """Add search button to render tree."""
        if self.data:
            # item = self.data[0]
            button = form_button(self.view_name, action, {}, 'search')
            self.buttons = [button]

    def asdict(self):
        """Create dictionary representation of render tree."""
        result = dict([(key, getattr(self, key)) for key in self.nodes])
        return result

    def dump(self, name):
        if setting.debug:
            write_file(name, encode_dict(self.asdict()))


class BareItemView:
    """Bare view class.

    This bare view class does not define routes. It serves as superclass for
    ItemView and for view classes that define their own specific routes.
    """
    model = 'BareItem'
    view_name = ''

    def __init__(self, request, params, model, action):
        """Constructor method for BareItemView.

        Forbidden method names: request, params, model, tree.

        Attributes:
            * request (Request):    HTTP request (WebOb)
            * params  (MultiDict):  route parameters (match.groupdict)
            * model   (Item):       model class
            * tree    (RenderTree): render tree object
        """
        self.request = request
        self.params = params
        self.model = model
        self.tree = RenderTree(request, model, self.view_name, action)
        self.form = {}

class ItemView(BareItemView):
    """Base class for views that implement the Atom Publishing protocol.

    ItemView is a base class for views that implement the Atom Publishing protocol:
    create, index, new, update, delete, edit, show. It defines extension methods
    for searching, which is a variation of 'index'.
    """
    model = 'Item'
    sort = []
    item_buttons = ['index', 'search', 'modify', 'delete']
    item_buttons_extra = []
    collection_buttons = ['index', 'search', 'new']
    collection_buttons_extra = []

    def show_item(self, item_or_id):
        """Prepare render tree for showing one item."""
        tree = self.tree
        tree.add_item(item_or_id)
        tree.add_buttons(self.item_buttons+self.item_buttons_extra)
        tree.flatten_item()
        tree.prune_item(depth=2)
        return tree.asdict()

    def show_items(self, action):
        tree = self.tree
        tree.add_cursor(action)
        tree.move_cursor()
        tree.add_items(['show', 'modify', 'delete'], self.sort)
        tree.add_buttons(self.collection_buttons+self.collection_buttons_extra)
        self.tree.dump('grid0.json')
        tree.flatten_items()
        self.tree.dump('grid1.json')
        tree.prune_items(depth=1)
        self.tree.dump('grid2.json')
        return tree.asdict()

    def convert_form(self, keep_empty=False):
        """Convert request parameters to unflattened dictionary."""
        raw_form = {key:value for key, value in self.request.params.items()
                              if (value or keep_empty) and not key.startswith('_')}
        self.form = unflatten(raw_form)

    def extract_item(self, prefix=None, model=None):
        """Convert unflattened form to item."""
        if prefix: # select fields whose keys start with prefix, remove 'prefix.' as we proceed
            prefix += '.'
            n = len(prefix)
            selection = {key[n:]:value for key, value in self.form.items()
                                       if key.startswith(prefix)}
        else:
            selection = self.form
        return (model if model else self.model).convert(selection)

    def write_and_show_item(self, item, description):
        tree = self.tree
        item.write(validate=False)
        tree.message = '{} {}'.format(description, str(item))
        return self.show_item(item)

    @route('/{id:objectid}', template='show')
    def show(self):
        """Show one item."""
        return self.show_item(self.params['id'])

    @route('/index', method='GET,POST', template='index')
    def index(self):
        """Show multiple items (collection)."""
        return self.show_items('index')

    @route('/search', template='form')
    def search(self):
        """Make a search form."""
        tree = self.tree
        tree.add_item(self.model.empty())
        tree.add_search_button('match')
        tree.flatten_item()
        tree.prune_item(depth=1, clear=True, form=True)
        return tree.asdict()

    @route('/match', method='GET,POST', template='index')
    def match(self):
        """Show the result list of a search."""
        return self.show_items('match')

    def update_item(self, item, initial, action, method):
        tree = self.tree
        if not initial:
            self.convert_form()
            item.update(self.extract_item())
            validation = item.validate(item)
            if validation['status'] == SUCCESS:
                return self.write_and_show(item, 'Modified item')
        tree.style = 0 if initial else 1
        tree.message = '{} {} has validation errors {}'.\
                       format('Modified item', str(item), validation['data'])
        tree.add_item(item)
        tree.add_form_buttons(action, method)
        tree.flatten_item()
        tree.prune_item(depth=2, form=True, clear=False)
        return tree.asdict()

    def create_item(self, item, initial, action, method):
        tree = self.tree
        if not initial:
            self.convert_form()
            item.update(self.extract_item())
            validation = item.validate(item)
            if validation['status'] == SUCCESS:
                return self.write_and_show(item, 'New item')
        tree.style = 0 if initial else 1
        tree.message = '{} {} has validation errors {}'.\
                       format('New item', str(item), validation['data'])
        tree.add_item(item)
        tree.add_form_buttons(action, method)
        tree.flatten_item()
        tree.prune_item(depth=2, form=True, clear=True)
        return tree.asdict()

    @route('/{id:objectid}/modify', template='form')
    def modify(self):
        """Make a form for modify/update action."""
        return self.update_item(self.model.lookup(self.params['id']), initial=True, action='update', method='PUT')

    @route('/{id:objectid}', method='PUT', template='show;form')
    def update(self):
        """Update an existing item."""
        return self.update_item(self.model.lookup(self.params['id']), initial=False, action='update', method='PUT')

    @route('/new', template='form')
    def new(self):
        """Make a form for new/create action."""
        return self.create_item(self.model.empty(), initial=True, action='create', method='POST')

    @route('', method='POST', template='show;form')
    def create(self):
        """Create a new item."""
        return self.create_item(self.model.empty(), initial=False, action='create', method='POST')

    @route('/{id:objectid}', method='DELETE', template='delete')
    def delete(self):
        """Delete one item in a functional sense.

        Items are not permanently removed, e.g. item.remove(), but marked as
        inactive. Permanent removal can be done by a clean-up routine, if necessary.
        """
        item = self.model.lookup(self.params['id'])
        result = item.set_field('active', False)
        if result['status'] == SUCCESS:
            result['data'] = 'item {} set to inactive'.format(str(item))
        else:
            result['data'] = 'item {} not modified'.format(str(item))
        return result
