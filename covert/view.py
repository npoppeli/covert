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
from .common import SUCCESS, write_file, logger
from .common import decode_dict, encode_dict, show_dict
from .model import unflatten, mapdoc
from . import setting

def show_value(s):
    if isinstance(s, list):
        return "[{}]".format(', '.join([str(el) for el in s]))
    else:
        return str(s)

def show_item(label, item):
    fmt = "{:<15}: {!s:<35}"
    print(label)
    print(fmt.format('veld', 'inhoud'))
    print('-' * 60)
    for key in sorted(item.keys()):
        value = show_value(item[key])
        if key == '_id' or value == '':
            continue
        print(fmt.format(key, value))
    print('\n')

def str2int(s):
    """Convert str to integer, or otherwise 0."""
    try:
        number = int(s)
    except:
        number = 0
    return number

setting.icons = {
    'show'   : 'fa fa-eye',
    'sort'   : 'fa fa-sort-amount-asc',
    'index'  : 'fa fa-list-alt',
    'search' : 'fa fa-search',
    'match'  : 'fa fa-search',
    'modify' : 'fa fa-pencil',
    'update' : 'fa fa-pencil',
    'new'    : 'fa fa-new',
    'create' : 'fa fa-new',
    'delete' : 'fa fa-trash-o',
    'expand' : 'fa fa-plus-square-o',
    'shrink' : 'fa fa-minus-square-o',
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
     'show'         : 'Show|Toon|Show',
     'sort'         : 'Sort|Sorteer|Sortera',
     'index'        : 'Browse|Blader|Bläddra',
     'search'       : 'Search|Zoek|Sök',
     'match'        : 'Match|Resultaat|Resultat',
     'modify'       : 'Modify|Wijzig|Ändra',
     'update'       : 'Update|Wijzig|Ändra',
     'new'          : 'New|Nieuw|Ny',
     'create'       : 'Create|Maak|Skapa',
     'delete'       : 'Delete|Verwijder|Radera',
     'expand'       : 'Expand|Vergroot|Utbreda',
     'shrink'       : 'Shrink|Verklein|Krympa',
     'home'         : 'Home|Begin|Hem',
     'info'         : 'Info|Info|Info',
     'ok'           : 'OK|OK|OK',
     'refresh'      : 'Refresh|Ververs|Fylla på',
     'cancel'       : 'Cancel|Annuleer|Upphäva'
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
    def __init__(self, pattern, method='GET', template='', icon='', label='', alias=''):
        """Constructor for 'route' decorator.

        Attributes:
            * pattern  (str): URL pattern, given as a format string
            * method   (str): string identifying HTTP method (e.g. 'GET' or 'GET, POST')
            * template (str): name(s) of template(s) that render(s) the result of the view
            * icon     (str): icon name for this route
            * label    (str): label for this route
        """
        self.pattern  = pattern
        self.method   = method
        self.template = template
        self.icon     = icon
        self.label    = label
        self.alias    = alias
    def __call__(self, wrapped):
        wrapped.pattern  = self.pattern
        wrapped.method   = self.method
        wrapped.template = self.template
        wrapped.icon     = self.icon
        wrapped.label    = self.label
        wrapped.alias    = self.alias
        return wrapped

# regular expressions used in routes
patterns = {
    'alpha'   : r'[a-zA-Z]+',
    'digits'  : r'\d+',
    'ids'     : r'\d+(?:\s+\d+)*',
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
        item_buttons_extra = []
        collection_buttons_extra = []
        for member_name, member in getmembers(view_class, isfunction):
            if hasattr(member, 'pattern'): # this member (method) is a route
                full_pattern  = '/' + view_name + member.pattern
                pattern       = route2pattern(full_pattern)
                regex         = route2regex(full_pattern)
                templates     = [] # each route has one or more templates
                for name in member.template.split(';'):
                    template_name = view_name+'_' + name
                    parent_name   = 'item_'       + name
                    if template_name in setting.templates:
                        templates.append(template_name)
                    elif parent_name in setting.templates:
                        templates.append(parent_name)
                    else:
                        templates.append('default')
                if member.icon:
                    if member_name in setting.icons:
                        logger.debug('Attempt to redefine icon for %s', member_name)
                    else:
                        setting.icons[member_name] = member.icon
                        item_buttons_extra.append(member_name)
                if member.label:
                    if member_name in setting.labels:
                        logger.debug('Attempt to redefine label for %s', member_name)
                    else:
                        setting.labels[member_name] = member.label
                for method in member.method.split(','):
                    setting.patterns[view_name+'_'+member_name] = pattern
                    setting.routes.append(Route(pattern, method, templates,
                        re.compile(regex), view_class, member_name))
                    if member.alias:
                        setting.routes.append(Route(member.alias, method, templates,
                            re.compile('^'+member.alias+'$'), view_class, member_name))
        view_class.item_buttons_extra = item_buttons_extra
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
    default = {'skip':0, 'limit':20, 'incl':0, 'dir':0, 'submit':''}

    def __init__(self, request, model):
        """Constructor method for Cursor.

        Attributes:
            * skip      (int):     URL pattern
            * limit     (int):     HTTP method
            * incl      (int):     1 if inactive items are included, 0 otherwise
            * dir       (int):     direction of browsing
            * filter    (str):     filter to pass to storage engine
            * query     (str):     transformed dictionary
            * prev      (bool):    True if 'previous' button enabled
            * next      (bool):    True if 'next' button enabled
            * action    (str):     form action
            * submit    (str):     value of the form button that was pressed
        """
        initial = '_skip' not in request.params
        for key, value in self.default.items():
            setattr(self, key, value)
        self.query = {}
        form = {}
        for key, value in request.params.items():
            if key == '_query': # query is in display form, so some fields need conversion
                for field, cond in decode_dict(value).items():
                    if field in model.cmap:
                        self.query[field] = tuple([cond[0]] + list(map(model.cmap[field], cond[1:])))
                    else:
                        self.query[field] = tuple(cond)
            elif key.startswith('_'):
                setattr(self, key[1:], str2int(value) if key[1:] in self.default else value)
            elif value:
                form[key] = value
        if initial: # initial post
            # flatten list-valued conditions
            self.query = {key:(value[0] if isinstance(value, list) else value)
                          for key, value in mapdoc(model.qmap, unflatten(form)).items()}
            logger.debug("cursor_init (initial): self.query=%s", self.query)
        else: # follow-up post
            logger.debug("cursor_init (follow-up): self.query=%s", self.query)

    def __str__(self):
        d = dict([(key, getattr(self, key, '')) for key in self.__slots__])
        return encode_dict(d)

    def asdict(self):
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

def js_button(view_name, action, item):
    """Create render-tree element for Javascript button."""
    return {'label': label_for(action), 'icon': icon_for(action),
            'name': action}

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
            * action    (str):     name of route (view method)
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
        self.poly = True
        self.status = '' # success, fail, error
        self.style = 0
        self.title = ''

    def add_cursor(self, action):
        """Add cursor object to render tree."""
        self.cursor = Cursor(self.request, self.model)
        self.cursor.action = url_for(self.view_name, action, {})

    def move_cursor(self):
        """Move cursor to new position.

        The actual filter used in the search is built from the search query given by
        the form, and an extra condition depending on the value of cursor.incl.
        """
        cursor = self.cursor
        cursor.filter = {} if cursor.incl == 1 else {'active': ('==', True)}
        # translate interval specifications in query
        for key, value in cursor.query.items():
            if isinstance(value, dict): # dict that wasn't recognized by mapdoc as sub-document
                convert = self.model.cmap[key]
                value_keys = sorted(value.keys())
                if  value_keys == ['from', 'to']:
                    cursor.query[key] = ('[]', convert(value['from']), convert(value['to']))
                elif value_keys == ['from']:
                    cursor.query[key] = ('==', convert(value['from']))
        cursor.filter.update(cursor.query)
        logger.debug("move_cursor: filter=%s", cursor.filter)
        count = self.model.count(cursor.filter)
        logger.debug("move_cursor: count=%d", count)
        cursor.skip = max(0, min(count, cursor.skip+cursor.dir*cursor.limit))
        cursor.prev = cursor.skip>0
        cursor.next = cursor.skip+cursor.limit < count

    def add_item(self, oid_or_item, prefix='', hide=None):
        """Add item to render tree."""
        item = self.model.lookup(oid_or_item) if isinstance(oid_or_item, str) else oid_or_item
        item['_buttons'] = []
        item['_prefix'] = prefix+'.' if prefix else ''
        item['_hide'] = hide == 'all'
        item['_hidden'] = [] if hide is None or hide == 'all' else hide
        # TODO: move lines below to event handler
        self.data.append(item)
        if 'active' in self.info:
            self.info['active'].append(item['active'])
        else:
            self.info['active'] = [item['active']]
        now, delta = datetime.now(), timedelta(days=10)
        recent = now-item['mtime']<delta
        if 'recent' in self.info:
            self.info['recent'].append(recent)
        else:
            self.info['recent'] = [recent]

    def add_items(self, buttons):
        """Add list of items to render tree."""
        self.data = []
        self.poly = False
        items = self.model.find(self.cursor.filter,
                                limit=self.cursor.limit, skip=self.cursor.skip)
        if items:
            logger.debug('add_items: count={}'.format(len(items)))
            active, recent = [], []
            now, delta = datetime.now(), timedelta(days=10)
            for item in items:
                button_list = [(delete_button if button == 'delete' else
                                normal_button)(self.view_name, button, item) for button in buttons]
                item['_buttons'] = button_list
                item['_prefix'] = ''
                item['_hide'] = False
                item['_hidden'] = []
                self.data.append(item)
                active.append(item['active'])
                recent.append(now - item['mtime'] < delta)
            self.info['active'] = active
            self.info['recent'] = recent
        else:
            query = []
            for key, value in self.cursor.query.items():
                cond = value[0] if isinstance(value, list) else value
                if len(cond) == 2:
                    query.append("{} {} {}".format(key, cond[0], cond[1]))
                else:
                    query.append("{} {} {}, {}".format(key, cond[0], cond[1], cond[2]))
            self.message = 'Nothing found for this query: ' + ', '.join(query)

    def flatten_item(self, nr=0, form=False):
        """Flatten one item in the render tree."""
        item = self.data[nr]
        item_meta = item.meta
        flat_item = item.display().flatten()
        newitem = OrderedDict()
        for key, value in flat_item.items():
            if key.startswith('_'):
                newitem[key] = value
            else:
                path = key.split('.')
                button_list = []
                if path[-1].isnumeric():
                    field = path[-2]
                    field_meta = item_meta[field]
                    pos = int(path[-1])+1
                    if pos == 1:
                        label = field_meta.label
                        if form:
                            button_list = [js_button(self.view_name, 'expand', item),
                                           js_button(self.view_name, 'shrink', item)]
                    else:
                        label = str(pos)
                else:
                    field = path[-1]
                    field_meta = item_meta[field]
                    label  = field_meta.label
                proplist = {'label': label, 'enum': field_meta.enum, 'schema': field_meta.schema,
                            'multiple': field_meta.multiple,
                            'formtype': 'hidden' if field_meta.auto else field_meta.formtype,
                            'auto': field_meta.auto, 'control': field_meta.control}
                newitem[key] = {'value':value, 'meta':proplist, 'buttons':button_list}
        newitem['_keys'] = [k for k in newitem.keys() if not k.startswith('_')]
        self.data[nr] = newitem

    def flatten_items(self, form=False):
        """Flatten all items in the render tree."""
        for nr in range(len(self.data)):
            self.flatten_item(nr=nr, form=form)

    def prune_item(self, nr=0, depth=2, clear=False, form=False):
        """Prune one item in the render tree."""
        item = self.data[nr]
        hidden = item['_hidden']
        newitem = OrderedDict()
        for key, field in item.items():
            if key.startswith('_'):
                newitem[key] = field
            elif (key.count('.') < depth) and key not in hidden and \
                not (form and field['meta']['schema']=='itemref'):
                if clear: field['value'] = ''
                newitem[key] = field
        newitem['_keys'] = [k for k in newitem.keys() if not k.startswith('_')]
        self.data[nr] = newitem

    def prune_items(self, depth=2, clear=False, form=False):
        """Prune all items in the render tree."""
        if self.poly:
            for nr in range(len(self.data)):
                self.prune_item(nr=nr, depth=depth, clear=clear, form=form)
        else:
            for nr, item in enumerate(self.data):
                hidden = item['_hidden']
                newitem = OrderedDict()
                for key, field in item.items():
                    if key.startswith('_'):
                        newitem[key] = field
                    else:
                        field_meta = field['meta']
                        if (key.count('.') < depth) and key not in hidden and not \
                            (field_meta['multiple'] or field_meta['auto'] or
                            field_meta['schema'] in ('text', 'memo', 'itemref')):
                            newitem[key] = field
                    newitem['_keys'] = [k for k in newitem.keys() if not k.startswith('_')]
                self.data[nr] = newitem

    def add_buttons(self, buttons):
        """Add buttons (normal and delete) to render tree."""
        if self.data:
            item = self.data[0]
            self.buttons = [(delete_button if button == 'delete' else
                             normal_button)(self.view_name, button, item) for button in buttons]

    def add_form_buttons(self, action, method=None):
        """Add form buttons to render tree.

           Arguments:
             method (str): HTTP method.

           Returns: None
        """
        if self.data:
            item = self.data[0]
            self.buttons = [form_button(self.view_name, action, item, 'ok')]
            if method:
                self.method = method

    def add_search_button(self, action):
        """Add search button to render tree."""
        if self.data:
            item = self.data[0]
            button = form_button(self.view_name, action, item, 'search')
            self.buttons = [button]

    def asdict(self):
        """Create dictionary representation of render tree."""
        result = dict([(key, getattr(self, key)) for key in self.nodes])
        if result.get('cursor', None):
            result['cursor'] = result['cursor'].asdict()
            result['cursor']['query'] = encode_dict(result['cursor']['query'])
        result['data'] = [item for item in result['data'] if not item['_hide']]
        return result

    def dump(self, name):
        if setting.debug:
            d = self.asdict()
            write_file(name, show_dict(d))


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
        tree.prune_item()
        return tree.asdict()

    def show_items(self, action):
        tree = self.tree
        tree.add_cursor(action)
        tree.move_cursor()
        tree.add_items(['show', 'modify', 'delete'])
        tree.add_buttons(self.collection_buttons+self.collection_buttons_extra)
        self.tree.dump('showitems0.json')
        tree.flatten_items()
        self.tree.dump('showitems1.json')
        tree.prune_items(depth=1)
        self.tree.dump('showitems2.json')
        return tree.asdict()

    def convert_form(self, keep_empty=False):
        """Convert request parameters to unflattened dictionary."""
        raw_form = {key:value for key, value in self.request.params.items()
                              if (value or keep_empty) and not key.startswith('_')}
        logger.debug("convert_form: raw form=%s", raw_form)
        self.form = unflatten(raw_form)
        logger.debug("convert_form: unflattened=%s", self.form)

    def extract_item(self, prefix=None, model=None):
        """Convert unflattened form to item."""
        # after unflattening, this is easy
        selection = self.form[prefix.rstrip('.')] if prefix else self.form
        logger.debug("extract_item: selection=%s", selection)
        return (model or self.model).convert(selection)

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
        tree.add_item(self.model())
        tree.add_search_button('match')
        self.tree.dump('search0.json')
        tree.flatten_item()
        self.tree.dump('search1.json')
        tree.prune_item(clear=True, form=True)
        self.tree.dump('search2.json')
        return tree.asdict()

    @route('/match', method='GET,POST', template='index')
    def match(self):
        """Show the result list of a search."""
        return self.show_items('match')

    def build_form(self, description, action, bound=False, postproc=None, method='POST',
                   clear=False, keep_empty=False):
        """Prepare render tree for rendering as a form.

        This function handles simple forms (single item) and multi-faceted forms (multiple items,
        not necessarily the same model). A form is called 'bound' if it contains user input
        (a concept borrowed from Django) and otherwise 'unbound'.

        Arguments:
            description (str):  description of form.
            action      (str):  URL for submit button.
            bound       (bool): form contains user input.
            postproc    (func): function to perform optional post-processing after validation.
            method      (str):  HTTP method, usually 'POST' or 'PUT'.
            clear       (bool): clear form (used in new/create forms).
            keep_empty  (bool): keep empty values (used in modify/update forms).

        Returns:
            None.
        """
        tree = self.tree
        validation = []
        if bound:
            self.convert_form(keep_empty=keep_empty)
            for item in tree.data:
                if not item['_hide']:
                    item.update(self.extract_item(prefix=item['_prefix'], model=type(item)))
                    validation.append(item.validate(item))
            if all([v['status']==SUCCESS for v in validation]):
                if callable(postproc):
                    postproc(tree)
                for item in tree.data:
                    item.write(validate=False)
                tree.title = ''
                tree.message = '{} {}'.format(description, str(tree.data[0]))
                return self.show_item(tree.data[0])
            else:
                errors = '\n'.join([v['data'] for v in validation])
                tree.message = '{} {} has validation errors {}'.\
                               format(description, str(tree.data[0]), errors)
                tree.style = 1
        tree.add_form_buttons(action, method)
        tree.flatten_items(form=True)
        tree.prune_items(form=True, clear=clear)
        return tree.asdict()

    @route('/{id:objectid}/modify', template='form')
    def modify(self):
        """Make a form for modify/update action."""
        self.tree.add_item(self.model.lookup(self.params['id']))
        return self.build_form(description='Modified item', action='update', method='PUT')

    @route('/{id:objectid}', method='PUT', template='show;form')
    def update(self):
        """Update an existing item."""
        self.tree.add_item(self.model.lookup(self.params['id']))
        return self.build_form(description='Modified item', action='update', method='PUT',
                               bound=True, keep_empty=True)

    @route('/new', template='form')
    def new(self):
        """Make a form for new/create action."""
        self.tree.add_item(self.model())
        return self.build_form(description='New item', action='create', clear=True)

    @route('', method='POST', template='show;form')
    def create(self):
        """Create a new item."""
        self.tree.add_item(self.model())
        return self.build_form(description='New item', action='create', clear=True, bound=True)

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
