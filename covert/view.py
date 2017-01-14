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
from .common import InternalError, SUCCESS, logger
from .common import decode_dict, encode_dict, show_dict
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
   'show'   : 'fa fa-eye',
   'diagram': 'fa fa-tree',
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
    """Return icon for route 'name'."""
    return setting.icons.get(name, 'fa fa-flash')

setting.labels = {
     'show'   : 'Show|Toon|Show',
     'diagram': 'Tree|Boom|Träd',
     'index'  : 'Browse|Blader|Bläddra',
     'search' : 'Search|Zoek|Sök',
     'match'  : 'Match|Resultaat|Resultat',
     'modify' : 'Modify|Wijzig|Ändra',
     'update' : 'Update|Wijzig|Ändra',
     'new'    : 'New|Nieuw|Ny',
     'create' : 'Create|Maak|Skapa',
     'delete' : 'Delete|Verwijder|Radera',
     'home'   : 'Home|Begin|Hem',
     'info'   : 'Info|Info|Info',
     'ok'     : 'OK|OK|OK',
     'refresh': 'Refresh|Ververs|Fylla på',
     'cancel' : 'Cancel|Annuleer|Upphäva'
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
            self.query = decode_dict(self.query)

    def __str__(self):
        d = dict([(key, getattr(self, key, '')) for key in self.__slots__])
        return show_dict(d)

    def asdict(self):
        self.query = encode_dict(self.query)
        return dict([(key, getattr(self, key, '')) for key in self.__slots__])

def normal_button(view_name, route_name, item):
    """Create render-tree element for normal button."""
    return {'label': label_for(route_name), 'icon': icon_for(route_name),
            'action': url_for(view_name, route_name, item), 'method':'GET'}

def form_button(view_name, route_name, item, button_name):
    """Create render-tree element for form button."""
    return {'label': label_for(button_name), 'icon': icon_for(button_name),
            'name': button_name,
            'action': url_for(view_name, route_name, item), 'method':'POST'}

def delete_button(view_name, route_name, item):
    """Create render-tree element for delete button."""
    return {'label': label_for(route_name), 'icon': icon_for(route_name),
            'action': url_for(view_name, route_name, item), 'method':'DELETE'}

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
             'message', 'meta', 'method', 'status', 'style', 'title']
    def __init__(self, request, model, view_name, route_name):
        """Constructor method for RenderTree.

        Attributes:
            * request   (Request): HTTP request (WebOb)
            * model     (Item):    model class
            * view_name (str):     name of view class
            * route_name(str):     name of route (view method)
        """
        # attributes for request handling
        self.request = request
        self.model = model
        self.view_name = view_name
        self.route_name = route_name
        # attributes that are used in rendering
        self.buttons = []
        self.cursor = None
        self.data = None
        self.info = {}
        self.message = ''
        self.meta = None
        self.method = ''
        self.status = '' # success, fail, error
        self.style = 0
        self.title = ''

    def add_cursor(self, route_name):
        """Add cursor object to render tree."""
        self.cursor = Cursor(self.request, self.model)
        self.cursor.action = url_for(self.view_name, route_name, {})

    def move_cursor(self):
        """Move cursor to new position.

        The actual filter used in the search is built from the search query specified by the user
        in the form, and an extra condition depending on the value of cursor.incl.
        """
        cursor = self.cursor
        cursor.filter = {} if cursor.incl == 1 else {'active':('==', True)}
        cursor.filter.update(cursor.query)
        count = self.model.count(cursor.filter)
        cursor.skip = max(0, min(count, cursor.skip+cursor.dir*cursor.limit))
        cursor.prev = cursor.skip>0
        cursor.next = cursor.skip+cursor.limit < count

    def add_item(self, oid_or_item):
        """Add item to render tree."""
        if isinstance(oid_or_item, str):
            item = self.model.lookup(oid_or_item)
            self.info['active'] = item['active']
            self.info['recent'] = datetime.now()-item['mtime'] < timedelta(days=7) and item['active']
        else:
            item = oid_or_item
        self.data = item

    def add_empty_item(self):
        """Add empty item to render tree."""
        self.data = self.model.empty()

    def add_items(self, buttons, sort):
        """Add list of items to render tree."""
        items = self.model.find(self.cursor.filter,
                                limit=self.cursor.limit, skip=self.cursor.skip, sort=sort)
        self.data = []
        active = []
        recent = []
        delta = timedelta(days=7)
        now = datetime.now()
        if not items:
            qs = ', '.join(["{}{}{}".format(k, v[0], v[1]) for k, v in self.cursor.query.items()])
            self.message += 'Nothing found for query {}'.format(qs)
            return self
        for item in items:
            button_list = [(delete_button if button == 'delete' else
                            normal_button)(self.view_name, button, item) for button in buttons]
            self.data.append({'item': item, 'buttons': button_list})
            active.append(item['active'])
            recent.append(now-item['mtime'] < delta and item['active'])
        self.info['active'] = active
        self.info['recent'] = recent

    def flatten_item(self):
        """Flatten the item in the render tree."""
        self.data = self.data.display().flatten()

    def flatten_items(self):
        """Flatten all items in the render tree."""
        for row in self.data:
            row['item'] = row['item'].display().flatten()

    def prune_item(self, depth, clear=False, form=False):
        """Prune the item in the render tree."""
        item_meta = self.model.meta
        meta, item = OrderedDict(), OrderedDict()
        for key, value in self.data.items():
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
            if (key.count('.') < depth) and not\
               (field_meta.schema=='itemref' and form):
                item[key] = '' if clear else value
                meta[key] = {'label'   : label,
                             'enum'    : field_meta.enum,
                             'formtype': 'hidden' if field_meta.auto else field_meta.formtype,
                             'auto'    : field_meta.auto,
                             'control' : field_meta.control}
        self.data, self.meta = item, meta

    def prune_items(self, depth):
        """Prune all items in the render tree."""
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

    def add_buttons(self, buttons):
        """Add buttons (normal and delete) to render tree."""
        if self.data:
            item = self.data[0]['item'] if isinstance(self.data, list) else self.data
            self.buttons = [(delete_button if button == 'delete' else
                             normal_button)(self.view_name, button, item) for button in buttons]

    def add_form_buttons(self, route_name, method=None):
        """Add form buttons to render tree."""
        if self.data:
            item = self.data
            self.buttons = [form_button(self.view_name, route_name, item, 'ok')]
            if method: # hide method (e.g. PUT) inside the form
                self.method = method

    def add_search_button(self, route_name):
        """Add search button to render tree."""
        if self.data:
            # item = self.data[0]['item']
            button = form_button(self.view_name, route_name, {}, 'search')
            self.buttons = [button]

    def asdict(self):
        """Create dictionary representation of render tree."""
        if self.cursor:
            self.cursor = self.cursor.asdict()
        result = dict([(key, getattr(self, key)) for key in self.nodes])
        if setting.debug:
            print(show_dict(result))
        return result


class BareItemView:
    """Bare view class.

    This bare view class does not define routes. It serves as superclass for
    ItemView and for view classes that define their own specific routes.
    """
    model = 'BareItem'
    view_name = ''

    def __init__(self, request, matches, model, route_name):
        """Constructor method for BareItemView.

        Forbidden method names: request, params, model, tree.

        Attributes:
            * request (Request):    HTTP request (WebOb)
            * params  (MultiDict):  route parameters (match.groupdict)
            * model   (Item):       model class
            * tree    (RenderTree): render tree object
        """
        self.request = request
        self.params = matches
        self.model = model
        self.tree = RenderTree(request, model, self.view_name, route_name)


class ItemView(BareItemView):
    """Base class for views that implement the Atom Publishing protocol.

    ItemView is a base class for views that implement the Atom Publishing protocol:
    create, index, new, update, delete, edit, show. It defines some extension methods
    for searching, which is a variation of 'index'.
    """
    model = 'Item'
    sort = []
    item_buttons = ['index', 'search', 'modify', 'delete']
    item_buttons_extra = []
    collection_buttons = ['index', 'search', 'new']
    collection_buttons_extra = []

    @route('/{id:objectid}', template='show')
    def show(self):
        """Show one item."""
        tree = self.tree
        tree.add_item(self.params['id'])
        tree.add_buttons(self.item_buttons+self.item_buttons_extra)
        tree.flatten_item()
        tree.prune_item(2)
        return tree.asdict()

    @route('/index', method='GET,POST', template='index')
    def index(self):
        """Show multiple items (collection)."""
        tree = self.tree
        tree.add_cursor('index')
        tree.move_cursor()
        tree.add_items(['show', 'modify', 'delete']+self.item_buttons_extra, self.sort)
        tree.add_buttons(self.collection_buttons+self.collection_buttons_extra)
        tree.flatten_items()
        tree.prune_items(1)
        return tree.asdict()

    @route('/search', template='form')
    def search(self):
        """Make a search form."""
        tree = self.tree
        tree.add_empty_item()
        tree.add_search_button('match')
        tree.flatten_item()
        tree.prune_item(1, clear=True, form=True)
        return tree.asdict()

    @route('/match', method='GET,POST', template='index')
    def match(self):
        """Show the result list of a search."""
        tree = self.tree
        tree.add_cursor('match')
        tree.move_cursor()
        tree.add_items(['show', 'modify', 'delete']+self.item_buttons_extra, self.sort)
        tree.add_buttons(self.collection_buttons+self.collection_buttons_extra)
        tree.flatten_items()
        tree.prune_items(1)
        return tree.asdict()

    @route('/new', template='form')
    def new(self):
        """Make a form for new/create action."""
        tree = self.tree
        tree.add_empty_item()
        # data = [{'item': item1, 'buttons': buttons1}, {'item': item2, 'buttons': buttons2}, ...]
        # where buttons is usually []
        # for repeatable fields, there are buttons Add and Remove
        tree.add_form_buttons('create')
        tree.flatten_item()
        tree.prune_item(2, clear=True, form=True)
        return tree.asdict()

    @route('/{id:objectid}/modify', template='form')
    def modify(self):
        """Make a form for modify/update action."""
        tree = self.tree
        tree.add_item(self.params['id'])
        tree.add_form_buttons('update', 'PUT')
        tree.flatten_item()
        tree.prune_item(2, form=True)
        return tree.asdict()

    def convert_form(self, keep_empty=False):
        """Convert request parameters to form content in model shape."""
        raw_form = {}
        for key, value in self.request.params.items():
            if (value or keep_empty) and not key.startswith('_'):
                raw_form[key] = value
        return self.model.convert(unflatten(raw_form))

    @route('/{id:objectid}', method='PUT', template='show;form')
    def update(self):
        """Update an existing item."""
        # fetch item from database and update with converted form contents
        item = self.model.lookup(self.params['id'])
        form = self.convert_form(keep_empty=True)
        item.update(form)
        logger.debug(">> update: updated item\n{}".format(show_dict(item)))
        validation = item.validate(item)
        tree = self.tree
        if validation['status'] == SUCCESS:
            result = item.write(validate=False)
            if result['status'] == SUCCESS:
                tree.message = 'Modified item {}'.format(str(item))
                tree.add_item(item)
                tree.add_buttons(self.item_buttons+self.item_buttons_extra)
                tree.flatten_item()
                tree.prune_item(2)
            else: # exception, in theory this should never occur
                raise InternalError('Modified item {} could not be stored ({})'.\
                            format(str(item), result['data']))
        else:
            tree.style = 1
            tree.message = 'Modified item {} has validation errors {}'.\
                            format(str(item), validation['data'])
            logger.error("Modified item\n{}\nhas validation errors\n{}".\
                         format(show_dict(item), validation['data']))
            tree.add_item(item)
            tree.add_form_buttons('update', 'PUT')
            tree.flatten_item()
            tree.prune_item(2, form=True)
        return tree.asdict()

    @route('', method='POST', template='show;form')
    def create(self):
        """Create a new item."""
        # fetch item from database and update with converted form contents
        item = self.model.empty()
        form = self.convert_form()
        item.update(form)
        validation = item.validate(item)
        logger.debug(">> create: new item\n{}".format(show_dict(item)))
        tree = self.tree
        if validation['status'] == SUCCESS:
            result = item.write(validate=False)
            if result['status'] == SUCCESS:
                tree.message = 'New item {}'.format(str(item))
                tree.add_item(item)
                tree.add_buttons(self.item_buttons+self.item_buttons_extra)
                tree.flatten_item()
                tree.prune_item(2)
            else: # exception, in theory this should never occur
                raise InternalError('New item {} could not be stored ({})'.\
                            format(str(item), result['data']))
        else:
            tree = self.tree
            tree.style = 1
            tree.message = 'New item {} has validation errors {}'.\
                            format(str(item), validation['data'])
            logger.debug("New item has validation errors", tree.message)
            tree.add_item(item)
            tree.add_form_buttons('create', 'POST')
            tree.flatten_item()
            tree.prune_item(2, form=True, clear=True)
        return tree.asdict()

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
