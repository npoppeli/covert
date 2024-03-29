# -*- coding: utf-8 -*-
"""Objects and functions related to view(s).

Views are classes consisting of route methods and other methods. The route methods
are decorated by '@route'. Each route has a URL pattern, one or more HTTP methods,
and one or more templates.

In the present implementation, form validation is performed on the server.
Alternative: do form validation in the client, using a suitable JavaScript library or framework.
"""

import calendar, logging, re
from collections import OrderedDict, defaultdict
from datetime import datetime
from inspect import getmembers, isclass, isfunction
from itertools import chain
from urllib.parse import urlencode
from .atom import empty_scalar, empty_dict, empty_list, atom_codemap
from .common import SUCCESS, FAIL, ERROR, write_file, str2int, show_dict
from .common import encode_dict, CATEGORY_READ, format_json_diff
from .model import empty_reference
from .event import event
from . import common as c
from . import setting
logger = logging.getLogger('covert')

# Routes and buttons
setting.labels = {
     'show'   : c._('Show'),
     'sort'   : c._('Sort'),
     'index'  : c._('Browse'),
     'search' : c._('Search'),
     'match'  : c._('Match'),
     'modify' : c._('Modify'),
     'update' : c._('Update'),
     'new'    : c._('New'),
     'create' : c._('Create'),
     'delete' : c._('Delete'),
     'push'   : c._('Push'),
     'pop'    : c._('Pop'),
     'home'   : c._('Home'),
     'info'   : c._('Info'),
     'ok'     : c._('OK'),
     'refresh': c._('Refresh'),
     'return' : c._('Return'),
     'cancel' : c._('Cancel')
}

def label_for(name):
    """Look up label for route 'name'."""
    return setting.labels.get(name, 'unknown')

def icon_for(name):
    """Look up icon for action 'name'."""
    return setting.icons.get(name, '')

def button_for(name):
    """Look up button for route 'name'."""
    return setting.buttons[name]

def url_for(name, item, query=None):
    """Generate URL for route 'name'."""
    url = setting.patterns[name].format(**item)
    if query:
        url += '?' + urlencode(query)
    return url

class Button:
    """Representation of a button.

    A button is a callable object. When a button is 'called', it expects one argument,
    namely an instance of the Item class. This Item instance is used to fill in some parts
    of the URL that should be called when the button is clicked.
    """
    __slots__ = ('uid', 'label', 'icon', 'action', 'method', 'vars',
                 'name', 'param', 'plabel', 'ptype', 'order')

    def __init__(self, view_uid, action, vars=None, method='GET', name='',
                 param='', plabel='', ptype='', order=0):
        """Constructor method for Button.

        Attributes:
            * view_uid (str) : unique id of view/method combination
            * action   (str) : URL pattern for view method
            * vars     (list): list of variable names of this route
            * method   (str) : HTTP method
            * name     (str) : button name, e.g. for submit buttons in forms
            * param    (str) : name of query parameter
            * plabel   (str) : label of query parameter
            * ptype    (str) : type of query parameter
            * order    (int) : sequence number of corresponding route (in order of definition)
        """
        key = view_uid.split('_', 1)[1]
        self.uid       = view_uid
        self.label     = label_for(key)
        self.icon      = icon_for(key)
        self.action    = action
        self.vars      = [] if vars is None else vars
        self.method    = method
        self.name      = name
        self.param     = param
        self.plabel    = plabel
        self.ptype     = ptype
        self.order     = order

    def __str__(self):
        d = dict([(key, getattr(self, key, '')) for key in self.__slots__])
        return str(d)

    def __call__(self, item, **kwarg):
        """Render button as dictionary, which can be included in the render tree.
        The extra keyword arguments can be used to customize button properties."""
        d = dict((key, getattr(self, key, '')) for key in self.__slots__)
        if d['action'] and item:
            d['action'] = d['action'].format(**item)
        for key, value in kwarg.items():
            d[key] = value
        return d

class Route:
    """Route definition.

    The definitions of all routes in all views are stored in the global variable setting.routes.
    """
    def __init__(self, pattern, method, vars, templates, regex, cls, name, order,
                 param, plabel, ptype, category=CATEGORY_READ):
        """Constructor method for Route.

        A Route object consists of (1) attributes that uniquely define the route,
        and (2) attributes that are needed by the controller to call the route.

        Attributes:
            * pattern   (str):   URL pattern
            * method    (str):   HTTP method
            * vars      (list):  list of variables contained in `pattern`
            * templates (list):  list of template names (at least 1)
            * regex     (regex): compiled regular expression
            * cls       (class): view class
            * name      (str):   method name
            * uid       (str):   unique id of route
            * order     (int):   sequence number of route (in order of definition)
            * param     (str):   query parameter for this route
            * plabel    (str):   label for this query parameter
            * ptype     (str):   type of this parameter (as in "<input type='value'>")
            * category  (int):   category used to determine permissions (CRUD)
        """
        self.pattern   = pattern
        self.method    = method
        self.vars      = vars
        self.templates = templates
        self.regex     = regex
        self.cls       = cls
        self.name      = name
        self.uid       = '{}_{}'.format(cls.__name__.replace('View', '', 1).lower(), name)
        self.order     = order
        self.param     = param
        self.plabel    = plabel
        self.ptype     = ptype
        self.category  = category

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

    def __init__(self, pattern, method='GET', template='', icon='', label='',
                 param='', plabel='', ptype='', category=CATEGORY_READ):
        """Constructor for 'route' decorator.

        Attributes:
            * pattern  (str): URL pattern, given as a format string
            * method   (str): string identifying HTTP method (e.g. 'GET' or 'GET, POST')
            * template (str): name(s) of template(s) that render(s) the result of the view
            * icon     (str): icon name for this route
            * label    (str): label for this route
            * param    (str): query parameter for this route
            * plabel   (str): label for this query parameter
            * ptype    (str): type of this parameter (as in "<input type='value'>")
            * category (int): category used to determine permissions (CRUD)
        """
        self.pattern   = pattern
        self.method    = method
        self.template  = template
        self.icon      = icon
        self.label     = label
        self.param     = param
        self.plabel    = plabel
        self.ptype     = ptype
        self.category  = category

    def __call__(self, wrapped):
        self._incr()
        wrapped.pattern  = self.pattern
        wrapped.method   = self.method
        wrapped.template = self.template
        wrapped.icon     = self.icon
        wrapped.label    = self.label
        wrapped.param    = self.param
        wrapped.plabel   = self.plabel
        wrapped.ptype    = self.ptype
        wrapped.order    = self.counter
        wrapped.category = self.category
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

def route2vars(pattern):
    """Create list of variable names that occur in `pattern`.

        Arguments:
        pattern (str): URL pattern.

    Returns:
        list: list of variable names.
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
    for key, value in setting.labels.items():
        setting.labels[key] = c._(value)
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
                route_name   = view_name + '_' + member_name
                full_pattern = '/' + view_name + member.pattern
                pattern      = route2pattern(full_pattern)
                regex        = route2regex(full_pattern)
                vars         = route2vars(full_pattern)
                templates    = [] # each route has one or more templates
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
                        pass
                    else:
                        setting.icons[member_name] = member.icon
                if member.label:
                    if member_name in setting.labels:
                        pass
                    else:
                        setting.labels[member_name] = member.label
                for method in member.method.split(','):
                    setting.patterns[route_name] = pattern
                    routes.append(Route(pattern, method, vars, templates, re.compile(regex),
                                        view_class, member_name, member.order,
                                        member.param, member.plabel, member.ptype))
        # sort routes by declaration order and add this to view class
        view_class._routes = sorted(routes, key=lambda r: r.order)
        # add routes to setting.routes, which will be sorted at the end
        setting.routes.extend(routes)

    # All views have been processed, so all routes are known. Now sort the routes in
    # reverse alphabetical order to ensure words such as 'match' and 'index' are not
    # absorbed by {id} or other components of the regex patterns
    setting.routes.sort(key=lambda r: r.pattern, reverse=True)

re_year = re.compile('^\d{4}$')
re_year_month = re.compile('^\d{4}-\d{2}$')
re_year_month_day = re.compile('^\d{4}-\d{2}-\d{2}$')

def preprocess_form(form):
    """Preprocess form
     1. convert parameters of date type, e.g. '1720' becomes '1720-01-01'.
     2. remove empty values

    Returns: set of date parameters."""
    # Step 1: convert parameters of date type
    date_params = set()
    form_keys = sorted(form.keys())
    for key in form_keys:
        path = key.split('.')
        if len(path) > 1 and path[2].startswith('d'):
            date_params.add(path[0])
    for date_param in date_params:
        params = [key for key in form_keys if key.startswith(date_param)]
        if len(params) == 1:
            x, y = params[0] + '#0', params[0] + '#1'
            value = form[params[0]]
            if value:
                try:
                    begin, end = re.split(r'[,;]', value)
                except ValueError:
                    begin, end = value, ''
                begin = begin.strip()
                end = end.strip()
            else:
                begin, end = '', ''
            del form[params[0]]
            form[x], form[y] = begin, end
        else:
            raise ValueError('Date parameter has too many parts: '+date_param)
        # convert to proper date range
        byear, bmonth, bday = '', '', ''
        if re_year_month_day.match(begin):
            byear = begin.split('-')[0]
        elif re_year_month.match(begin):
            byear, bmonth = begin.split('-')
            form[x] += '-01'
        elif re_year.match(begin):
            byear = begin
            form[x] += '-01-01'
        if re_year_month_day.match(end):
            pass # no need to adjust anything
        elif re_year_month.match(end):
            eyear, emonth = end.split('-')
            eday = str(calendar.monthrange(int(eyear), int(emonth))[1])
            form[y] = f'{end}-{eday}'
        elif re_year.match(end):
            eyear = end
            emonth = int(bmonth) if bmonth else 12
            eday = str(calendar.monthrange(int(eyear), emonth)[1])
            emonth = str(emonth).zfill(2)
            form[y] = f'{end}-{emonth}-{eday}'
        elif end == '' and byear:
            eyear = byear
            emonth = int(bmonth) if bmonth else 12
            eday = str(calendar.monthrange(int(eyear), emonth)[1])
            emonth = str(emonth).zfill(2)
            form[y] = f'{eyear}-{emonth}-{eday}'
    # Step 2: remove empty (key, value) pairs
    form_keys = sorted(form.keys())
    for key in form_keys:
        if not form[key]:
            del form[key]
    return date_params

class Cursor:
    """Representation of the state of browsing through a collection of items.

    A cursor object represent the state of browsing through a collection of items.
    In HTML pages the cursor is represented as a form, with several buttons and toggles.

    For some attributes, default values are defined in the 'default' dictionary.
    """
    __slots__ = ('skip', 'limit', 'incl', 'dir', 'operator', 'count',
                 'filter', 'form', 'prev', 'next', 'action', 'method', 'submit')
    default = {'skip': 0, 'limit': 20, 'incl': 0, 'dir': 0, 'count': 0, 'submit': ''}

    def __init__(self, request, model):
        """Constructor method for Cursor. This method scans the request parameters and
        divides them into three parts:
        1. form contents (values of query, required)
        2. operator vector (operators in query, optional)
        3. cursor (used by the 'index' and 'search' routes)

        Request parameters are taken from the body of a POST request and the
        URL string of a GET request:

        field1=value1&field2=value2&field3=value3...

        On an initial request for multiple items, either /item/index or /item/search,
        the request parameter _filter is absent. On follow-up requests, this parameter
        should be present.

        * Letters (A–Z and a–z), numbers (0–9) are left as-is.
        * The characters '*','-','.' and '_' are left as-is.
        * Characters that cannot be converted to the correct charset are replaced by
          HTML numeric character references.
        * The plus sign '+' is encoded by %2B.
        * SPACE is encoded as '+' or '%20'
        * All other characters are encoded as %HH hex representation with any non-ASCII
          characters first encoded as UTF-8 (or other specified encoding).

        Attributes:
            * skip      (int):     skip this number of items in query
            * limit     (int):     retrieve no more than this numbers of items
            * count     (int):     total number of items in query
            * incl      (int):     1 if inactive items are included, 0 otherwise
            * dir       (int):     direction of browsing
            * filter    (str):     filter to pass to storage engine
            * operator  (dict):    boolean operators for filter (unused feature)
            * form      (str):     transformed dictionary
            * prev      (bool):    True if 'previous' button enabled
            * next      (bool):    True if 'next' button enabled
            * action    (str):     form action
            * method    (str):     form method
            * submit    (str):     value of the form button that was pressed
        """
        for key, value in self.default.items():
            setattr(self, key, value)
        self.form = {}
        # TODO: apply this feature somewhere
        self.operator = {}
        self.filter = ''
        form = {}
        for key, value in request.params.items():
            if key == '_filter': # reuse filter that is included in request
                # logger.debug(f'init_cursor: filter={value}')
                self.filter = value
            elif key =='_skey': # standard field of Item that can be used in a search query
                form[key] = value
            elif key.startswith('_'): # cursor attribute
                attval = str2int(value) if key[1:] in self.default else value
                setattr(self, key[1:], attval)
            else: # form attribute
                form[key] = value.replace('\n', ' ').replace('\t', ' ')
        if '_filter' not in request.params:
            # Preprocess form: take care of empty values, and parameters of date type
            date_params = preprocess_form(form)
            converted_form = model.convert(form, partial=True)
            for key, value in converted_form.items():
                # ignore values that are empty in a functional sense
                if empty_scalar(value) or empty_reference(value) or \
                   empty_dict(value) or empty_list(value):
                    # logger.debug(f"cursor: key '{key}' has empty value '{value}' - ignored")
                    continue
                if key in date_params:
                    self.form[key] = ('in', value[0], value[1])
                else:
                    if isinstance(value, list):
                        value0 = value[0] if value else ''
                    else:
                        value0 = value
                    if isinstance(value0, dict):
                        for (subkey, subvalue) in value0.items():
                            self.form[key+'.'+subkey] = (model.qmap[subkey], subvalue)
                    else:
                        self.form[key] = (model.qmap[key], value0)
            # logger.debug(f'cursor: converted form parameters={self.form}')

    def __str__(self):
        d = dict([(key, getattr(self, key, '')) for key in self.__slots__])
        return encode_dict(d)

    def __call__(self):
        d = dict([(key, getattr(self, key, '')) for key in self.__slots__])
        return d

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
    def __str__(self):
        return "Cookie(name='{}', value='{}', path='{}', expires='{}')".\
                format(self.name, self.value, self.path, self.expires)

regex_active = re.compile("\(active\s*=\s*.+?\)")
regex_andand = re.compile('and\s*and')

def remove_active(s):
    """Remove term `(active == foo)` from filter expression `s`"""
    result = regex_andand.sub(' and ', regex_active.sub('', s)).strip()
    # remove loose 'and' at begin or end of string
    if result.startswith('and'):
        result = result[3:]
    if result.endswith('and'):
        result = result[:-3]
    return result.strip()

def preprocess_lists(item):
    """"Pre-process empty lists: add one element with default value(s)."""
    item_meta = item.meta
    for key in item.keys():
        value = item[key]
        if key not in item_meta: continue
        field_meta = item_meta[key]
        if not field_meta.multiple or value or field_meta.code == '^': continue
        if field_meta.schema == 'dict':
            default = {k: atom_codemap[item_meta[k].code].default for k in field_meta.enum}
        else:
            default = atom_codemap[field_meta.code].default
        item[key].append(default)
        # logger.debug(f"preprocess_lists: field '{key}' has modified value '{item[key]}'")

def display_item(item, form_type, view_name):
    """Prepare display form of one item for insertion into the render tree.
    The `form_type` parameter is used for additions to the render tree in a few cases:
      - form_type '': no additions
      - form_type 'modify': add push/pop buttons, pre-process empty lists
      - form_type 'search': substitute form type of date fields.
    """
    if form_type == 'modify':
        preprocess_lists(item)
    item_meta = item.meta
    disp_item = item.display()
    item_prefix = item.get('_iprefix', '')
    new_item = OrderedDict()
    has_buttons = defaultdict(bool)
    for key, value in disp_item.items():
        if key.startswith('_'):
            new_item[key] = value
            continue
        # keys are built up like this: [field].[sequence_number].[atom_type](#[index])?
        path = key.split('.')
        field, atom_type = path[0], path[2]
        if field in item_meta:
            field_meta = item_meta[field]
        else:
            logger.debug(f"Unknown meta field '{field}' in item; key={key}")
            continue
        schema = field_meta.schema
        is_itemref = schema == 'itemref'
        # TODO: disable, later remove this exception
        # if form_type == 'search' and is_itemref: continue
        multiple = field_meta.multiple
        button_list = []
        if multiple: # add push/pop buttons (in certain conditions)
            if '#' in key:
                index = int(key[key.find('#')+1:])
            else: # actual value is empty list
                index = 0
            if form_type == 'modify' and not is_itemref and index == 0 and not has_buttons[field]:
                # add buttons to first element in group (examples: notes.0.s#0)
                # itemref fields are excluded from this at the moment
                # TODO: view_name + '_' + action_name -> function
                push = Button(view_name+'_push', action='', name='push')
                pop  = Button(view_name+'_pop' , action='', name='pop' )
                button_list.append(push(item))
                button_list.append(pop(item))
                has_buttons[field] = True
            # set label and metadata
            if field not in item_meta:
                logger.info(f'display_item: discard extra field {key}={value} (multiple)')
                continue
            label = field_meta.label if index == 0 else str(index+1)
        else:
            index = -1
            if field not in item_meta:
                logger.info(f'display_item: discard extra field {key}={value} (not multiple)')
                continue
            label = field_meta.label
        if field_meta.auto:
            field_formtype = 'hidden'
        elif form_type == 'search'  and field_meta.formtype == 'date':
            field_formtype = 'daterange'
        else:
            field_formtype = field_meta.formtype
        proplist = {'label': label, 'enum': field_meta.enum, 'index': index+1,
                    'schema': field_meta.schema, 'multiple': field_meta.multiple,
                    'locked': is_itemref, 'scalar': is_itemref,
                    'formid': item_prefix + key, 'formtype': field_formtype,
                    'auto': field_meta.auto, 'control': field_meta.control}
        new_item[key] = {'value':value, 'meta':proplist, 'buttons':button_list}
    new_item['_keys'] = [k for k in new_item.keys() if not k.startswith('_')]
    return new_item

class RenderTree:
    """Tree representation of information created by a route.

    The information that is created by a route (view method) is collected in the render tree.
    This is returned to the controller as a dictionary. The controller serializes this
    dictionary and returns the result to the web client.

    Some elements of the render tree are temporary (needed for the request handling). The other
    attributes are specified by the class attribute 'nodes'. These attributes are used by the
    __call__() method.
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
        self.status = SUCCESS # sensible default; other values are FAIL, ERROR
        self.style = 0
        self.title = ''

    def add_cursor(self, action):
        """Add cursor object to render tree."""
        self.cursor = Cursor(self.request, self.model)
        self.cursor.action = url_for(self.view_name+'_'+action, {})

    def move_cursor(self):
        """Move cursor to new position.

        Initially, the filter used in the search is built from the form contents,
        and an extra condition depending on the value of cursor.incl.
        On follow-up posts, the filter is rebuilt from a pickle, and only the 'active'
        term (if present) needs to be inspected for possible adjustment.
        """
        cursor = self.cursor
        create_filter = '_filter' not in self.request.params
        debug_filter = setting.debug > 1
        if create_filter:
           # cursor.form contains query specifications with real values
           if debug_filter: logger.debug(f'move_cursor: create filter from form={cursor.form}')
           for key, value in cursor.form.items():
               if isinstance(value, list):
                   cursor.form[key] = ('in', value[0], value[1])
           filter_spec = {} if cursor.incl == 1 else {'active': ('==', '1')}
           filter_spec.update(cursor.form)
           # translate filter dictionary to expression
           terms = []
           for key, value in filter_spec.items():
               emap = self.model.emap.get(key.split('.')[-1], None)
               if len(value) == 3:
                   v1, v2 = (emap(value[1]), emap(value[2])) if emap else (value[1], value[2])
                   term = f"({key} {value[0]} ({v1}, {v2}))"
               else:
                   v1 = emap(value[1]) if emap else value[1]
                   term = f"({key} {value[0]} {v1})"
               terms.append(term)
           cursor.filter = ' and '.join(terms)
           if debug_filter: logger.debug(f'move_cursor: filter built from form={cursor.filter}')
        else:
            if debug_filter: logger.debug(f'move_cursor: filter passed with request={cursor.filter}')
            if cursor.incl == 1: # remove term 'active=1' from filter (if present)
                if 'active' in cursor.filter:
                    cursor.filter = remove_active(cursor.filter)
            elif 'active' not in cursor.filter: # add term 'active=1' to filter (unless already present)
                cursor.filter += " and (active == '1')"
            if debug_filter: logger.debug(f'move_cursor: adjusted filter={cursor.filter}')
        cursor.count = self.model.count(cursor.filter)
        cursor.skip = max(0, min(cursor.count, cursor.skip+cursor.dir*cursor.limit))
        cursor.prev = cursor.skip > 0
        cursor.next = cursor.skip+cursor.limit < cursor.count

    def add_item(self, oid_or_item, prefix='', label='', hide=None):
        """Add item to render tree."""
        if oid_or_item is None:
            raise ValueError(f'add_item: oid_or_item is None')
        elif isinstance(oid_or_item, str):
            item = self.model.lookup(oid_or_item)
        else:
            item = oid_or_item
        event('additem:init', item, self)
        item['_buttons'] = []
        item['_iprefix'] = prefix+'.' if prefix else ''
        item['_ilabel'] = label
        item['_hidden'] = [] if hide is None else hide
        event('additem:pre', item, self)
        self.data.append(item)
        event('additem:post', item, self)

    def add_items(self, buttons):
        """Add list of items to render tree."""
        self.poly = False
        items = self.model.find(self.cursor.filter,
                                limit=self.cursor.limit, skip=self.cursor.skip)
        if items:
            event('additem:init', items[0], self)
            for item in items:
                item['_buttons'] = []
                for button in buttons:
                    item['_buttons'].append(button(item))
                item['_iprefix'] = ''
                item['_hidden'] = []
                event('additem:pre', item, self)
                self.data.append(item)
                event('additem:post', item, self)
        else:
            origin = self.request.cookies.get('search-origin', 'index')
            self.add_return_button(origin)
            self.message += c._('No results for search query:') + '\n' + str(self.cursor.filter)

    def display_item(self, nr=0, form_type=''):
        """Display one item in the render tree.
        The `form_type` parameter is used for additions to the render tree in a few cases:
          - form_type '': no additions
          - form_type 'modify': add push/pop buttons
          - form_type 'search': scan form type of date fields.
        """
        self.data[nr] = display_item(self.data[nr], form_type, self.view_name)

    def display_items(self, form_type=''):
        """Display all items in the render tree."""
        for nr in range(len(self.data)):
            self.display_item(nr=nr, form_type=form_type)

    def prune_item(self, nr=0, clear=False):
        """Prune one item in the render tree."""
        item = self.data[nr]
        hidden = item['_hidden']
        item_prefix = item.get('_iprefix', '')
        pruned_keys = []
        for key, field in item.items():
            if key.startswith('_'):
                pass # do not add this key to pruned_keys
            else:
                if clear:
                    item[key]['value'] = ''
                excluded = key in hidden or \
                           (item_prefix and field['meta']['schema'] == 'itemref')
                if not excluded:
                    pruned_keys.append(key)
        # logger.debug(f'prune_item: _ikeys={pruned_keys}')
        item['_ikeys'] = pruned_keys

    def prune_items(self, clear=False, omit=None):
        """Prune all items in the render tree."""
        omit_from_index = omit or []
        if self.poly:
            for nr in range(len(self.data)):
                self.prune_item(nr=nr, clear=clear)
        else:
            pruned_keys = []
            for nr, item in enumerate(self.data):
                hidden = item['_hidden']
                for key, field in item.items():
                    path = key.split('.')
                    if key.startswith('_'):
                        pass # do not add this key to pruned_keys
                    else:
                        field_meta = field['meta']
                        excluded = key in hidden or key in omit_from_index or \
                                   field_meta['multiple'] or \
                                   field_meta['auto'] or path[1] != '0' or \
                                   field_meta['schema'] in ('text', 'memo')
                        if not excluded:
                            pruned_keys.append(key)
                item['_ikeys'] = pruned_keys
                pruned_keys = []
            # logger.debug(f'prune_items: _ikeys={pruned_keys}')

    def add_buttons(self, buttons):
        """Add buttons to render tree."""
        if self.data:
            item = self.data[0]
            for button in buttons:
               self.buttons.append(button(item))

    def add_form_buttons(self, action, method=None):
        """Add form buttons to render tree.

           Arguments:
             action (str): ...
             method (str): HTTP method.

           Returns: None
        """
        if self.data:
            item = self.data[0]
            # TODO: view_name + '_' + action_name should move to a function
            button = button_for(self.view_name+'_'+action)
            ok     = button(item, name='ok',     label=c._('OK'),     icon=icon_for('ok'))
            cancel = button(item, name='cancel', label=c._('Cancel'), icon=icon_for('cancel'))
            self.buttons.append(ok)
            self.buttons.append(cancel)
            if method:
                self.method = method

    def add_search_buttons(self, action):
        """Add search buttons to render tree."""
        if self.data:
            item = self.data[0]
            # TODO: view_name + '_' + action_name should move to a function
            # TODO: also add to item:
            # TODO: _search=1, _placeholder='jjjj-mm-dd' I18N, label='t/m' I18N
            button = button_for(self.view_name+'_'+action)
            search = button(item, name='search', label=c._('Search'), icon=icon_for('search'))
            cancel = button(item, name='cancel', label=c._('Cancel'), icon=icon_for('cancel'))
            self.buttons.append(search)
            self.buttons.append(cancel)

    def add_return_button(self, location):
        """Add return button to render tree."""
        # TODO: view_name + '_' + action_name should move to a function
        button = Button(self.view_name+'_return', action=location)
        go = button(None, label=c._('Return'), icon=icon_for('return'))
        self.buttons.append(go)

    def __call__(self):
        """Create dictionary representation of render tree."""
        result = dict([(key, getattr(self, key)) for key in self.nodes])
        if result.get('cursor', None):
            result['cursor'] = result['cursor']()
        return result

    def dump(self, name):
        if setting.debug:
            d = self()
            timestamp = datetime.now().strftime('_%H%M%S') if setting.debug > 1 else ''
            write_file(name+timestamp+'.json', show_dict(d))


class BareItemView:
    """Bare view class.

    This bare view class does not define routes. It serves as superclass for
    ItemView and for view classes that define their own specific routes.
    """
    model = 'BareItem'
    view_name = ''
    tree_class = RenderTree

    def __init__(self, request, params, model, action):
        """Constructor method for BareItemView.
        The tree class is a parameter, so that applications can define their
        own view classes and render-tree classes.

        Attributes:
            * request (Request):    HTTP request (WebOb)
            * params  (MultiDict):  route parameters (match.groupdict)
            * model   (Item):       model class
            * tree    (RenderTree): render tree object
        Do not use the attribute names above as method names in a sub-class!
        """
        self.request = request
        self.params = params
        self.model = model
        self.tree = self.tree_class(request, model, self.view_name, action)
        self.form = {}

class ItemView(BareItemView):
    """Base class for views that implement the Atom Publishing protocol.

    ItemView is a base class for views that implement the Atom Publishing protocol:
    create, index, new, update, delete, edit, show. It defines extension methods
    for searching, which is a variation of 'index'.
    """
    model = 'Item'
    view_name = 'item'
    item_buttons = 3
    omit_from_index = []

    def buttons(self, vars=None, ignore=None):
        """Make list of buttons for this view. Ignore buttons in `ignore`"""
        def usable(uid):
            return all(not uid.startswith(i) for i in ignore)

        selection = [btn for key, btn in setting.buttons.items()
                     if btn.method not in ('PUT', 'POST') and
                        key.startswith(self.view_name)]
        if vars:
            sub_selection = [btn for btn in selection if set(btn.vars) == set(vars)]
        else:
            sub_selection = [btn for btn in selection if set(btn.vars) == set() and not btn.param]
        if ignore:
            sub_selection = [btn for btn in sub_selection if usable(btn.uid.split('_', 1)[1])]
        return sorted(sub_selection, key=lambda btn: btn.order)

    def show_item(self, item):
        """Prepare render tree for showing one item."""
        tree = self.tree
        tree.add_item(item)
        tree.add_buttons(self.buttons(['id'], ignore=['show', 'delete']))
        tree.display_item()
        tree.prune_item()
        tree.title = "{} {}".format(self.model.trname(), str(item))
        tree.dump('show_item')
        return tree()

    def show_items(self, action):
        tree = self.tree
        tree.add_cursor(action)
        tree.move_cursor()
        buttons = self.buttons(['id'])[0:self.item_buttons]
        tree.add_items(buttons)
        tree.add_buttons(self.buttons([]))
        tree.display_items()
        tree.prune_items(omit=self.omit_from_index)
        tree.dump('show_items')
        return tree()

    @route('/{id:objectid}', template='show;empty')
    def show(self):
        """Show item identified by object id."""
        oid = self.params['id']
        item = self.model.lookup(oid)
        if item:
            return self.show_item(item)
        else:
            tree = self.tree
            tree.status = ERROR
            tree.message = _('Nothing found for id={}').format(oid)
            tree.style = 1
            return tree()

    @route('/index', method='GET,POST', template='index')
    def index(self):
        """Show multiple items (collection)."""
        return self.show_items('index')

    @route('/search', template='form')
    def search(self):
        """Make a search form, using an empty item to populate the form."""
        tree = self.tree
        tree.add_item(self.model())
        tree.add_search_buttons('match')
        tree.display_item(form_type='search')
        tree.prune_item(clear=True)
        tree.cookies.append(Cookie('search-origin', self.request.referer, path='/', expires=120))
        tree.dump('search')
        return tree()

    @route('/match', method='GET,POST', template='index')
    def match(self):
        """Show the result list of a search."""
        return self.show_items('match')

    def extract_form(self, model, prefix=None, keep_empty=False, raw=False):
        """Extract information from (part of) form to document. This method is used
        by the process_form() method - see below - but can also be used by applications.
        In simple forms, the raw form contains e.g.

            marriageplace.0.s: s1
            husbandname.0.s  : s2

        In this case, extract_form should be called with prefix='' or None.
        In composite forms, the raw form contains e.g.

            family.marriageplace.0.s: s1
            family.husbandname.0.s  : s2
            partner.firstname.0.s   : s3
            partner.birthplace.0.s  : s4

        In that case, extract_form should be called twice, once with prefix='family.'
        and once with prefix='partner.'.
        """
        params = self.request.params
        if prefix:
            raw_form = {key.replace(prefix, '', 1):value for key, value in params.items()
                        if (value or keep_empty) and key.startswith(prefix) and
                        not key.startswith(prefix+'_')}
        else:
            raw_form = {key:value for key, value in params.items()
                        if (value or keep_empty) and not key.startswith('_')}
        # Fields of 'itemref' type should not be in the request parameters.
        # If the application uses HTML forms, disabled fields are
        # not present in the request body (see W3C Specification for HTML 5).
        # logger.debug(f"extract_form: raw_form={raw_form}")
        if raw:
            return raw_form
        else:
            result = model.convert(raw_form, partial=True)
            # logger.debug(f"extract_form: converted form={result}")
            return result

    def process_form(self, description, action, bound=False, postproc=None, method='POST',
                     clear=False, keep_empty=False, diff=False):
        """Prepare render tree for rendering as a form.

        This function handles simple forms (single item) and multi-faceted forms (multiple items,
        not necessarily the same model). A form is called 'bound' if it contains user input and
        otherwise 'unbound'.

        Arguments:
            description (str):  description of form.
            action      (str):  URL for submit button.
            bound       (bool): form contains user input.
            postproc    (func): function to perform optional post-processing after validation.
                                Note: application-specific, cannot be replaced by event handlers!
            method      (str):  HTTP method, usually 'POST' or 'PUT'.
            clear       (bool): clear form (used in new/create forms).
            keep_empty  (bool): keep empty values (used in modify/update forms).

        Returns:
            dictionary form of tree.
        """
        tree = self.tree
        validations = []
        # keys to be deleted prior to writing
        delete_keys = ['_buttons', '_hidden', '_iprefix', '_ilabel']
        if bound:
            delta = []
            for item in tree.data:
                old = item.copy()
                prefix = item.get('_iprefix', '')
                result = self.extract_form(model=type(item), prefix=prefix,
                                           keep_empty=keep_empty)
                logger.debug(f"process_form: prefix={prefix} result={result}")
                item.update(result)
                if diff:
                    delta.append(format_json_diff(old, item))
                validations.append(item.validate(item))
            if all([validation['status'] == SUCCESS for validation in validations]):
                if callable(postproc):
                    postproc(tree)
                for item in tree.data:
                    # before persisting the item: remove the keys we added temporarily
                    for key in delete_keys:
                        if key in item: del item[key]
                    item.write(validate=False)
                tree.message = '{} {}. '.format(description, str(tree.data[0]))
                if diff:
                    tree.message += ''.join(delta)
                return self.show_item(tree.data[0])
            else:
                errors = '\n'.join([v['data'] for v in validations])
                logger.debug(f"process_form: {description} has validation errors {errors}")
                tree.message = c._('{} {} has validation errors {}').\
                               format(description, str(tree.data[0]), errors)
                tree.style = 1
                tree.status = ERROR
        tree.title = "{} {} {}".format(description, self.model.trname(), str(tree.data[0]))
        tree.add_form_buttons(action, method)
        tree.display_items(form_type='modify')
        tree.prune_items(clear=clear)
        tree.dump('process_form')
        return tree()

    @route('/{id:objectid}/modify', template='form')
    def modify(self):
        """Make a form for modify/update action."""
        tree = self.tree
        item = self.model.lookup(self.params['id'])
        tree.add_item(item)
        tree.title = "{} {}".format(self.model.trname(), str(item))
        return self.process_form(description=c._('Modify item'),
                                 action='update', method='PUT')

    @route('/{id:objectid}', method='PUT', template='show;form')
    def update(self):
        """Update an existing item."""
        submit = self.request.params['_submit']
        tree = self.tree
        if submit == 'ok': # modify item and show this
            item = self.model.lookup(self.params['id'])
            tree.add_item(item)
            return self.process_form(description=c._('Modified item'), bound=True,
                                     action='update', method='PUT', keep_empty=True, diff=True)
        else: # leave item unmodified and show this
            tree.message = c._('Item was not modified')
            return self.show_item(self.params['id'])

    @route('/new', template='form')
    def new(self):
        """Make a form for new/create action."""
        tree = self.tree
        tree.add_item(self.model())
        tree.title = "{} {}".format(self.model.trname(), 'new')
        return self.process_form(description=c._('New item'),
                                 action='create', clear=True)

    @route('', method='POST', template='show;form;index')
    def create(self):
        """Create a new item."""
        submit = self.request.params['_submit']
        tree = self.tree
        if submit == 'ok': # create item and show this
            tree.add_item(self.model())
            return self.process_form(description=c._('New item'), bound=True,
                                     action='create', clear=True)
        else: # show index page
            tree.style = 2
            tree.message = c._('No new item was created')
            return self.show_items('index')

    @route('/{id:objectid}', method='DELETE', template='delete')
    def delete(self):
        """Delete one item in a functional sense.

        Items are not permanently removed, e.g. item.remove(), but marked as
        inactive. Permanent removal can be done by a clean-up routine, if necessary.
        """
        item = self.model.lookup(self.params['id'])
        event('delete:pre', item, self)
        result = item.set_field('active', False)
        event('delete:post', item, self)
        if result['status'] == SUCCESS:
            result['data'] = f'item {item} set to inactive'
        else:
            result['data'] = f'item {item} not modified'
        return result