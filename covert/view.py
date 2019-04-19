# -*- coding: utf-8 -*-
"""Objects and functions related to view(s).

Views are classes consisting of route methods and other methods. The route methods
are decorated by '@route'. Each route has a URL pattern, one or more HTTP methods,
and one or more templates.

In the present implementation, form validation is performed on the server. Alternative:
do form validation in the client, using Parsley.js (jQuery) for example.
"""

from base64 import b64decode, b64encode
import pickle, re
from collections import OrderedDict
from datetime import datetime, timedelta
from inspect import getmembers, isclass, isfunction
from itertools import chain
from urllib.parse import urlencode
from .common import SUCCESS, write_file, logger
from .common import encode_dict, show_dict
from .model import unflatten, mapdoc, Filter, Term, Or
from . import setting

def str2int(s):
    """Convert str to integer, or otherwise 0."""
    try:
        number = int(s)
    except:
        number = 0
    return number

def icon_for(name):
    """Return icon for route 'name'."""
    return setting.icons.get(name, '')

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
     'return'       : 'Return|Terug|Retur',
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
    def __init__(self, pattern, method, params, templates, regex, cls, name, order):
        """Constructor method for Route.

        A Route object consists of (1) attributes that uniquely define the route,
        and (2) attributes that are needed by the controller to call the route.

        Attributes:
            * pattern   (str):   URL pattern
            * method    (str):   HTTP method
            * params    (list):  list of parameters contained in `pattern`
            * templates (list):  list of template names (at least 1)
            * regex     (regex): compiled regular expression
            * cls       (class): view class
            * name      (str):   method name
            * uid       (str):   unique id of route
            * order     (int):   sequence number of route (in order of definition)
        """
        self.pattern = pattern
        self.method = method
        self.params = params
        self.templates = templates
        self.regex = regex
        self.cls = cls
        self.name = name
        self.uid = '{}_{}'.format(cls.__name__.replace('View', '', 1).lower(), name)
        self.order = order

    def __str__(self):
        return("{} {} -> {}:{}, uid={} templates={}".
               format(self.pattern, self.method, self.cls.__name__, self.name,
                      self.uid, ', '.join(self.templates)))

class route:
    """Decorator for methods in a View class.

    This decorator adds attributes to methods. Once set, these attributes cannot be changed anymore.
    """
    counter = 0

    @classmethod
    def _incr(cls):
        cls.counter += 1

    def __init__(self, pattern, method='GET', template='', icon='', label=''):
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
    def __call__(self, wrapped):
        self._incr()
        wrapped.pattern  = self.pattern
        wrapped.method   = self.method
        wrapped.template = self.template
        wrapped.icon     = self.icon
        wrapped.label    = self.label
        wrapped.order    = self.counter
        return wrapped

# regular expressions used in routes
patterns = {
    'alpha'   : r'[a-zA-Z]+',
    'digits'  : r'\d+',
    'ids'     : r'\d+(?:\s+\d+)*',
    'objectid': r'\w{24}',
    'word'    : r'\w{2,20}'
}

def split_route(pattern):
    """Split route into components.

    Split route into components: a combined split on '{' and '}' results in a list of lists,
    and chain.from_iterable transforms this into a flat list.
    Routing arguments should have this form: '{name:pattern}', where pattern is one of the keys
    of the `patterns` dictionary (see above).

    Arguments:
        pattern (str): URL pattern.

    Returns:
        list: components of URL pattern.
    """
    return list(chain.from_iterable([p.split('}') for p in pattern.split('{')]))

def route2pattern(pattern):
    """Create formatting string from route specifier.

    Remove the pattern specifier from all routing arguments in `pattern`, so that
    we get a pattern acceptable to str.format().

    Arguments:
        pattern (str): URL pattern.

    Returns:
        str: string formatting pattern.
    """
    parts = split_route(pattern)
    parts[1::2] = list(map(lambda p: '{{{0}}}'.format(p.split(':')[0]), parts[1::2]))
    return ''.join(parts)

def route2params(pattern):
    """Create list of parameter names that occur in `pattern`.

        Arguments:
        pattern (str): URL pattern.

    Returns:
        list: list of parameter names.
    """
    def split_lookup(s):
        before, after = s.split(':')
        return before
    parts = split_route(pattern)
    return list(map(split_lookup, parts[1::2]))

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

    Read all views from the module object `module`. A view is a class that is
    a sub-class of BareItemView and has a name ending in 'View'.
    In each view, locate the members that are of 'function' type and have a 'pattern'
    attribute, indicating they have been decorated with '@route'. Those members are
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
        # TODO: this transformation happens in two places, should be one
        view_name = class_name.replace('View', '', 1).lower()
        view_class.view_name = view_name
        routes = []
        for member_name, member in getmembers(view_class, isfunction):
            if hasattr(member, 'pattern'): # this member (method) is a route
                full_pattern  = '/' + view_name + member.pattern
                pattern       = route2pattern(full_pattern)
                regex         = route2regex(full_pattern)
                params        = route2params(full_pattern)
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
                        logger.debug("Attempt to redefine icon for '%s''", member_name)
                    else:
                        # logger.debug("New icon '%s' for '%s'", member.icon, member_name)
                        setting.icons[member_name] = member.icon
                if member.label:
                    if member_name in setting.labels:
                        logger.debug("Attempt to redefine label for '%s'", member_name)
                    else:
                        # logger.debug("New label '%s' for '%s'", member.label, member_name)
                        setting.labels[member_name] = member.label
                for method in member.method.split(','):
                    setting.patterns[view_name+'_'+member_name] = pattern
                    routes.append(Route(pattern, method, params, templates,
                        re.compile(regex), view_class, member_name, member.order))
        # sort routes by declaration order and add this to view class
        view_class._routes = sorted(routes, key=lambda r: r.order)
        # add routes to setting.routes, which will be sorted at the end
        setting.routes.extend(routes)

    # All views have been processed, so all routes are known. Now sort the routes in
    # reverse alphabetical order to ensure words such as 'match' and 'index' are not
    # absorbed by {id} or other components of the regex patterns
    setting.routes.sort(key=lambda r: r.pattern, reverse=True)

class Cursor:
    """Representation of the state of browsing through a collection of items.

    A cursor object represent the state of browsing through a collection of items.
    In HTML pages the cursor is represented as a form, with several buttons and toggles.

    For some attributes, default values are defined in the 'default' dictionary.
    """
    __slots__ = ['skip', 'limit', 'incl', 'dir', 'operator', 'count',
                 'filter', 'form', 'prev', 'next', 'action', 'submit']
    default = {'skip': 0, 'limit': 20, 'incl': 0, 'dir': 0, 'count': 0, 'submit': ''}

    def __init__(self, request, model):
        """Constructor method for Cursor. This method scans the request parameters and
        divides them into three parts:
        1. form contents (values of query, required)
        2. operator vector (operators in query, optional)
        3. cursor (used by the 'index' and 'search' routes)

        Request parameters can be found in the body of a POST request or in the
        URL string of a GET request:

        field1=value1&field2=value2&field3=value3...

        Characters that cannot be converted to the correct charset are replaced with HTML numeric
        character references. SPACE is encoded as '+' or '%20'. Letters (A–Z and a–z), numbers (
        0–9) and the characters '*','-','.' and '_' are left as-is, + is encoded by %2B. All
        other characters are encoded as %HH hex representation with any non-ASCII characters
        first encoded as UTF-8 (or other specified encoding)

        Attributes:
            * skip      (int):     skip this number of items in query
            * limit     (int):     retrieve no more than this numbers of items
            * count     (int):     total number of items in query
            * incl      (int):     1 if inactive items are included, 0 otherwise
            * dir       (int):     direction of browsing
            * filter    (str):     filter to pass to storage engine
            * operator  (dict):    boolean operators for filter
            * form      (str):     transformed dictionary
            * prev      (bool):    True if 'previous' button enabled
            * next      (bool):    True if 'next' button enabled
            * action    (str):     form action
            * submit    (str):     value of the form button that was pressed
        """
        initial_post = '_skip' not in request.params
        for key, value in self.default.items():
            setattr(self, key, value)
        self.form = {}
        self.operator = {}
        form = {}
        for key, value in request.params.items():
            if key == '_filter': # rebuild filter that was saved in form
                decoded = b64decode(value.encode())
                self.filter = pickle.loads(decoded)
            elif key =='_skey':
                form[key] = value
            elif key.startswith('*'): # operator
                self.operator[key[1:]] = value
            elif key.startswith('_'):
                setattr(self, key[1:], str2int(value) if key[1:] in self.default else value)
            elif value:
                form[key] = value
        if initial_post: # add operators
            logger.debug('cursor.form: initial post, populate self.form')
            for key, value in mapdoc(model.qmap, unflatten(form, model)).items():
                # if value is a list, use the first element
                operator_value = value[0] if isinstance(value, list) else value
                if key in self.operator: # operator-value tuple with explicit operator
                    self.form[key] = (self.operator[key], operator_value[1])
                elif isinstance(value, dict): # not converted by mapdoc
                    self.form[key] = operator_value
                else: # operator-value tuple with default operator
                    self.form[key] = (operator_value[0], operator_value[1])
                logger.debug('cursor.form: {} -> {}'.format(key, str(self.form[key])))

    def __str__(self):
        d = dict([(key, getattr(self, key, '')) for key in self.__slots__])
        d['filter'] = b64encode(pickle.dumps(d['filter'])).decode()
        return encode_dict(d)

    def asdict(self):
        d = dict([(key, getattr(self, key, '')) for key in self.__slots__])
        d['filter'] = b64encode(pickle.dumps(d['filter'])).decode()
        return d

def get_button(view_name, action, item):
    """Create render-tree element for GET button."""
    return {'label': label_for(action), 'icon': icon_for(action),
            'action': url_for(view_name, action, item), 'method':'GET'}

def post_button(view_name, action, item, button_name):
    """Create render-tree element for POST button."""
    return {'label': label_for(button_name), 'icon': icon_for(button_name),
            'name': button_name,
            'action': url_for(view_name, action, item), 'method':'POST'}

def delete_button(view_name, action, item):
    """Create render-tree element for DELETE button."""
    return {'label': label_for(action), 'icon': icon_for(action),
            'action': url_for(view_name, action, item), 'method':'DELETE'}

def generic_button(view_name, action, item):
    """Create render-tree element for generic button."""
    return {'label': label_for(action), 'icon': icon_for(action),
            'name': action}

class Cookie:
    """Instances of this class define basic cookies as constituents of the render tree.

    Attributes:
        * see constructor method
    """

    __slots__ = ('name', 'value', 'path', 'expires')

    def __init__(self, name, value, path, expires=0):
        """Initialize cookie.

        Arguments:
            name    (str):     name of cookie (see Webob documentation)
            value   (str):     value of cookie (ibid)
            path    (str):     path for cookie (ibid)
            expires (integer): max-age of cookie (ibid)
        """
        self.name    = name
        self.value   = value
        self.path    = path
        self.expires = expires

class RenderTree:
    """Tree representation of information created by a route.

    The information that is created by a route (view method) is collected in the render tree.
    This is returned to the controller as a dictionary. The controller serializes this
    dictionary and returns the result to the web client.

    Some elements of the render tree are temporary (needed for the request handling). The other
    attributes are specified by the class attribute 'nodes'. These attributes are used by the
    asdict() method.
    """
    nodes = ['buttons', 'cursor', 'data', 'computed', 'cookies',
             'message', 'method', 'status', 'style', 'title']
    def __init__(self, request, model, view_name, action):
        """Constructor method for RenderTree.

        Attributes:
            * request   (Request): HTTP request (WebOb)
            * model     (Item):    model class
            * view_name (str):     name of view class
            * action    (str):     name of route (view method)
            * cookies   (list):    list of cookies to be set in the response object
        """
        # attributes for request handling
        self.request = request
        self.model = model
        self.view_name = view_name
        self.action = action
        self.cookies = []
        # attributes that are used in rendering
        self.buttons = []
        self.cursor = None
        self.data = [] # actual properties of item
        self.computed = {} # computed properties of item
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

        Initially, the filter used in the search is built from the form contents,
        and an extra condition depending on the value of cursor.incl.
        On follow-up posts, the filter is rebuilt from a pickle, and only the 'active'
        term (if present) needs to be looked at for possible adjustment.
        """
        cursor = self.cursor
        initial_post = '_skip' not in self.request.params
        if initial_post:
           # translate interval specifications in form
           for key, value in cursor.form.items():
               if isinstance(value, dict): # not converted by mapdoc
                   convert = self.model.cmap[key]
                   key_set = set(value.keys())
                   if  key_set == {'from', 'to'}:
                       cursor.form[key] = ('in', convert(value['from']), convert(value['to']))
                   elif key_set == {'from'}:
                       cursor.form[key] = ('==', convert(value['from']))
           filter_spec = {} if cursor.incl == 1 else {'active': ('==', True)}
           filter_spec.update(cursor.form)
           # translate filter dictionary to Filter object
           new_filter = Filter()
           for key, value in filter_spec.items():
               if key == 'active':
                   continue
               if len(value) == 3:
                   new_filter.add(Term(key, value[0], value[1], value[2]))
               else:
                   new_filter.add(Term(key, value[0], value[1]))
           cursor.filter = new_filter
           if 'active' in filter_spec:
               cursor.filter.add(Term('active', '==', True))
        else:
            # cursor.incl == 1: remove term 'active=True' (if present) from filter
            #             == 0: add term 'active=True' (if not present) to filter
            if cursor.incl == 1:
                if 'active' in cursor.filter:
                    del cursor.filter['active']
            elif 'active' not in cursor.filter:
                cursor.filter.add(Term('active', '==', True))
        cursor.count = self.model.count(cursor.filter)
        cursor.skip = max(0, min(cursor.count, cursor.skip+cursor.dir*cursor.limit))
        cursor.prev = cursor.skip>0
        cursor.next = cursor.skip+cursor.limit < cursor.count

    def add_item(self, oid_or_item, prefix='', hide=None):
        """Add item to render tree."""
        item = self.model.lookup(oid_or_item) if isinstance(oid_or_item, str) else oid_or_item
        item['_buttons'] = []
        item['_prefix'] = prefix+'.' if prefix else ''
        item['_hide'] = hide == 'all'
        item['_hidden'] = [] if hide is None or hide == 'all' else hide
        self.data.append(item)
        # TODO: move lines below to event handler
        now, delta = datetime.now(), timedelta(days=10)
        recent = now - item['mtime'] < delta
        if 'recent' in self.computed:
            self.computed['recent'].append(recent)
        else:
            self.computed['recent'] = [recent]

    def add_items(self, buttons):
        """Add list of items to render tree."""
        self.poly = False
        items = self.model.find(self.cursor.filter,
                                limit=self.cursor.limit, skip=self.cursor.skip)
        # TODO: move line below to event handler
        active, recent = [], []
        if items:
            # TODO: move line below to event handler
            now, delta = datetime.now(), timedelta(days=10)
            for item in items:
                button_list = [(delete_button if button == 'delete' else
                                get_button)(self.view_name, button, item) for button in buttons]
                item['_buttons'] = button_list
                item['_prefix'] = ''
                item['_hide'] = False
                item['_hidden'] = []
                self.data.append(item)
                # TODO: move line below to event handler
                active.append(item['active'])
                recent.append(now - item['mtime'] < delta)
        else:
            origin = self.request.cookies.get('search-origin', 'onbekend')
            self.add_return_button(origin)
            self.message += 'Geen resultaten voor zoekopdracht:\n{}'.format(self.cursor.filter.format())
        # TODO: move lines below to event handler
        self.computed['active'] = active
        self.computed['recent'] = recent

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
                depth = key.count('.')
                button_list = []
                if path[-1].isnumeric(): # TODO: add button also for source.[012].relations
                    field = path[-2]
                    field_meta = item_meta[field]
                    pos = int(path[-1])+1
                    if pos == 1:
                        label = field_meta.label
                        if form:
                            button_list = [generic_button(self.view_name, 'expand', item),
                                           generic_button(self.view_name, 'shrink', item)]
                    else:
                        label = str(pos)
                else:
                    field = path[-1]
                    field_meta = item_meta[field]
                    if depth == 0:
                        label = field_meta.label
                    else:
                        parent = path[0]
                        label = '{}.{}'.format(item_meta[parent].label, field_meta.label)
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
            else:
                excluded = (key.count('.') > depth) or (key in hidden) or \
                           (form and field['meta']['schema'] == 'itemref')
                if not excluded:
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
                        excluded = (key.count('.') > depth) or (key in hidden) or \
                                   field_meta['multiple'] or field_meta['auto'] or \
                                   field_meta['schema'] in ('text', 'memo', 'itemref')
                        if not excluded: newitem[key] = field
                newitem['_keys'] = [k for k in newitem.keys() if not k.startswith('_')]
                self.data[nr] = newitem

    def add_buttons(self, buttons):
        """Add buttons (normal and delete) to render tree."""
        if self.data:
            item = self.data[0]
            for button in buttons:
                factory = delete_button if button == 'delete' else get_button
                self.buttons.append(factory(self.view_name, button, item))

    def add_form_buttons(self, action, method=None):
        """Add form buttons to render tree.

           Arguments:
             action (str): ...
             method (str): HTTP method.

           Returns: None
        """
        if self.data:
            item = self.data[0]
            self.buttons.append(post_button(self.view_name, action, item, 'ok'))
            if method:
                self.method = method

    def add_search_button(self, action):
        """Add search button to render tree."""
        if self.data:
            item = self.data[0]
            button = post_button(self.view_name, action, item, 'search')
            self.buttons.append(button)

    def add_return_button(self, location):
        """Add return button to render tree."""
        button = {'label': label_for('return'), 'icon': icon_for('return'),
                  'action': location, 'method': 'GET'}
        self.buttons.append(button)

    def asdict(self):
        """Create dictionary representation of render tree."""
        result = dict([(key, getattr(self, key)) for key in self.nodes])
        if result.get('cursor', None):
            result['cursor'] = result['cursor'].asdict()
            result['cursor']['filter'] = encode_dict(result['cursor']['filter'])
        result['data'] = [item for item in result['data'] if not item['_hide']]
        return result

    def dump(self, name):
        if setting.debug:
            d = self.asdict()
            postfix = datetime.now().strftime('_%H%M%S.json')
            write_file(name+postfix, show_dict(d))


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
    view_name = 'item'
    grid_buttons = 3

    def routes(self, params=None):
        selection = [item for item in self._routes
                     if item.method not in ('PUT', 'POST') and item.uid.startswith(self.view_name)]
        result = selection if params is None else \
                 [item for item in selection if set(item.params) == set(params)]
        return [item.name for item in result]

    def show_item(self, item_or_id):
        """Prepare render tree for showing one item."""
        tree = self.tree
        tree.add_item(item_or_id)
        tree.add_buttons(self.routes(['id']))
        tree.flatten_item()
        tree.prune_item()
        return tree.asdict()

    def show_items(self, action):
        tree = self.tree
        tree.add_cursor(action)
        tree.move_cursor()
        routes = self.routes(['id'])[0:self.grid_buttons]
        tree.add_items(routes)
        tree.add_buttons(self.routes([]))
        tree.flatten_items()
        tree.prune_items(depth=1)
        return tree.asdict()

    def convert_form(self, keep_empty=False):
        """Convert request parameters to unflattened dictionary."""
        raw_form = {key:value for key, value in self.request.params.items()
                              if (value or keep_empty) and not key.startswith('_')}
        self.form = unflatten(raw_form, self.model)

    def extract_item(self, prefix=None, model=None):
        """Convert unflattened form to item."""
        # The first step is easy, thanks to unflattening.
        selection = self.form[prefix.rstrip('.')] if prefix else self.form
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
        tree.flatten_item()
        tree.prune_item(clear=True, form=True)
        tree.cookies.append(Cookie('search-origin', self.request.referer, path='/', expires=120))
        return tree.asdict()

    @route('/match', method='GET,POST', template='index')
    def match(self):
        """Show the result list of a search."""
        return self.show_items('match')

    def build_form(self, description, action, bound=False, postproc=None, method='POST',
                   clear=False, keep_empty=False):
        """Prepare render tree for rendering as a form.

        This function handles simple forms (single item) and multi-faceted forms (multiple items,
        not necessarily the same model). A form is called 'bound' if it contains user input and
        otherwise 'unbound'.

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
