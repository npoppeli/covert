# -*- coding: utf-8 -*-
"""
covert.view
-----
Objects and functions related to view(s).
In the present implementation, form validation is performed on the server. In a future version
it could be delegated to the client, using Parsley.js (jQuery) for example.
"""

import re, sys, traceback
from .common import str2int, encode_dict, decode_dict
from .model import BareItem
from .layout import node
from .report import logger, print_node, print_doc

# Maps and functions for actions, URL patterns, labels and icons
action_map = []
url_map = {}
label_map = {}
icon_map = {}

def exception_report(exc):
    """generate exception traceback in HTML form"""
    exc_type, exc_value, exc_trace = sys.exc_info()
    head = ["<p>Internal error. Traceback (most recent call last:</p>"]
    body = ["<p>{0}</p>".format(l.replace("\n", "<br/>"))
              for l in traceback.format_tb(exc_trace)]
    tail = ["<p><em>{0}: {1}</em></p>".format(exc_type.__name__, exc_value)]
    return ''.join(head+body+tail)

def register_view(view):
    assert isinstance(view, ItemView)
    # assert: view.model is in model map
    # view contains _map = [], array of tuples (regex, method, callable)
    action_map.extend(view._action)
    url_map.update(view._url)
    label_map.update(view._label)
    icon_map.update(view._icon)

def action_name(view, action):
    return view+':'+action

def url_for(view, action, qs={}, **kwarg):
    url = url_map.get(action_name(view, action), '').format(**kwarg)
    if qs:
        url = url + '?' + '&'.join(['{0}={1}'.format(k, qs[k]) for k in qs])
    return url

def label_for(view, action, **kwarg):
    return label_map.get(action_name(view, action), '')

def icon_for(view, action, **kwarg):
#TODO: authorization determines the state (enabled, disabled)
    return icon_map.get(action_name(view, action), '')

# functions for buttons
#TODO: these should become classes (button factories). Instances are partial functions
# with URL and other variables as parameters, and can be passed along to grid etcetera.
def panel_button(view, action, confirm=None, prompt=None, enabled=True, **kwarg):
    return node('button', 'panel',
                icon=icon_for(view, action), label=label_for(view, action),
                enabled=enabled, action=url_for(view, action, **kwarg),
                confirm=confirm, prompt=prompt)
def grid_button(view, action, confirm=None, prompt=None, enabled=True, **kwarg):
    return node('button', 'grid',
                icon=icon_for(view, action), label=label_for(view, action)[0],
                enabled=enabled, action=url_for(view, action, **kwarg),
                confirm=confirm, prompt=prompt)
def form_button(label, icon):
    return node('button', 'form',
                icon=icon, label=label, enabled=True, name='$submit', value=label)

# functions for transforming items into render trees
def build_item(item, genus):
    """
    build_item(item, genus, hide): node
    Create presentation node for display.
    """
    result = []
    for name in item.fields('short' if genus=='grid' else ''):
        field = item.skeleton[name]
        field_value = item[name]
        if field.multiple:
            childlist = [ node('show', field.schema, value=e) for e in field_value ]
        else:
            childlist = [ node('show', field.schema, value=field_value) ]
        result.append(node('field', genus,
                           label=field.label, children=childlist,
                           hidden=field.hidden, multiple=field.multiple))
    return node('item', genus, label=item.name, children=result, active=item['active'])

def build_form(item, error={}):
    """
    build_form(item, error): nodelist
    Create list of input nodes (included in a form).
    """
    result = []
    for name in item.fields('mutable'):
        field = item.skeleton[name]
        field_value = item[name]
        if field.multiple:
            childlist =  [ node('show', field.schema, value=e) for e in field_value  ]
        else:
            childlist = [ node('show', field.schema, value=field_value) ]
        #TODO: put error message in placeholder of corresponding form element, and
        # collect all error messages in text block below form
        result.append(node('input', field.schema, error=(name in error),
                      label=field.label, name=name, children=childlist,
                       auto=field.auto, multiple=field.multiple))
    return result

def build_empty_form(item, error={}):
    """
    build_empty_form(item, error): nodelist
    Create list of input nodes (included in a form).
    """
    result = []
    for name in item.fields('mutable'):
        field = item.skeleton[name]
        if name in error:
            logger.debug('empty_form: error in field '+name)
            result.append(node('input', field.schema, error=True,
                               label=field.label, name=name, content=error[name],
                               auto=field.auto, multiple=field.multiple))
        else:
            result.append(node('input', field.schema, error=False,
                               label=field.label, name=name, content='',
                               auto=field.auto, multiple=field.multiple))
    return result

# Cursor: class to represent state of search through item collection
class Cursor(dict):
    __slots__ = ('skip', 'limit', 'count', 'inin', 'inins', 'dir',
                 'query', 'bquery', 'equery', 'submit', 'error')
    _numbers  = ('skip', 'limit', 'count', 'inin', 'inins', 'dir')
    def __init__(self, model, request=None):
        self.skip, self.limit, self.count = 0, 10, 0
        self.inin, self.inins, self.dir = 0, 0, 0
        if request:
            query = {}
            for key, value in request.params.items():
                if key.startswith('$'):
                    newkey = key[1:]
                    setattr(self, newkey, str2int(value) if newkey in self._numbers else value)
                elif value:
                    query[key] = value
            if self.query == '': # initial post
                valid = model.validate(query, 'query')
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
        # equery = bquery (base query)+ query (user query)
        #   - bquery depends on active toggle
        #   - query is specified in form, or {}
        self.equery = {'active':'' if self.inin == 1 else True}
        self.equery.update(self.query)
        if (self.count == 0) or (self.inin != self.inins): # count absent or toggle has changed
            self.count = model.count(self.equery)
        if request:
            self.skip = max(0, min(self.count, self.skip+self.dir*self.limit))
    def form(self, action):
        qs = encode_dict(self.query) if self.query else ''
        return node('form', 'cursor', action=action, inin=self.inin, inins=self.inin,
                    skip=self.skip, count=self.count, limit=self.limit, query=qs,
                    enableprev=(self.skip>0), enablenext=(self.skip+self.limit<self.count))

# ItemView class, and decorator used for the view methods
class action:
    """
    action: decorator for methods in a View class. This adds attributes to methods.
    Once set, these attributes cannot be changed anymore.
    @action(label, icon, method, pattern)
    - label: label (visible name) of button
    - icon: identifier of icon used for button
    - method: string identifying HTTP method (e.g. 'GET' or 'GET, POST')
    - pattern: URL pattern, given as a format string
    """
    def __init__(self, label, icon, method, pattern):
        self.label = label; self.icon = icon
        self.method = method; self.pattern = pattern
    def __call__(self, wrapped):
        wrapped.label = self.label; wrapped.icon = self.icon
        wrapped.method = self.method; wrapped.pattern = self.pattern
        return wrapped

class ItemView:
    """
    View: class for view objects that implement the Atom Publishing protocol
    (create, index, new, update, delete, edit, show) plus extensions.
    The operations 'create', 'index' etcetera are called 'actions'.
    """
    model = BareItem
    def __init__(self):
        name = self.__class__.__name__
        # view classes must have a name that ends in 'View'
        assert len(name) > 4 and name[-4:] == 'View'
        # derive four maps that are used for routing, and for composing URLs and buttons
        self._action, self._url, self._label, self._icon = [], {}, {}, {}
        self.name = name.replace('View', '', 1).lower()
        #TODO: extend like this {variable:datatype}, datatype is 'word' (\w+),
        # 'alpha' ([a-zA-Z]+), digits (\d+), number (\d*\.?\d+), chunk ([^/^.]+)
        # or any (.+). Taken from Luke Arno's selector.
        id_param    = re.compile(r'\{(id)}')   # becomes '(?P<foo>\w+)'
        other_param = re.compile(r'\{(\w+)\}') # becomes '(?P<foo>[^/]+)'
        for name in dir(self):
            member = getattr(self, name)
            if hasattr(member, 'pattern'): # decorated method, i.e. an action
                full_pattern = '/' + self.name + member.pattern
                regex = other_param.sub(r'(?P<\1>[^/]+)',
                           id_param.sub(r'(?P<\1>\w+)', '^'+full_pattern+'$'))
                for method in member.method.split(','):
                    self._action.append((re.compile(regex), method, member))
                aname = action_name(self.name, name)
                self._url[aname] = full_pattern
                self._label[aname] = member.label
                self._icon[aname] = member.icon
        # sorting in reverse alphabetical order ensures words like 'match' and 'index'
        # are not absorbed by {id} or other components of the regex patterns
        self._action.sort(key=lambda action: action[0].pattern, reverse=True)

    def _show(self, item):
        """build page content for one item, plus buttons"""
        item_id = item['id']
        item_node = build_item(item, 'single')
        index  = panel_button(self.name, 'index')
        modify = panel_button(self.name, 'modify', id=item_id)
        delete = panel_button(self.name, 'delete', id=item_id, confirm='yes',
                              prompt='delete {0} {1}'.format(self.name, item_id))
        panel_node = node('panel', 'normal', children=[index, modify, delete])
        return item_node, panel_node

    @action('Show', 'photo', 'GET', '/{id}')
    def show(self, req, **kwarg):
        """display one item"""
        item = self.model.lookup(kwarg['id'])
        if item == None:
            return node('block', '', content='Nothing found for '+req.path)
        else:
            return self._show(item)

    @action('Search', 'search', 'GET', '/search')
    def search(self, req, error={}):
        """GET  /item/search: create empty search form"""
        form_action = url_for(self.name, 'match')
        search      = form_button('Search', 'search')
        panel_node  = node('panel', 'form', children=[search])
        childlist   = build_empty_form(self.model({}), error=error)
        childlist.append(panel_node)
        childlist.append(node('input', 'hidden', name='$query', value=''))
        form_node = node('form', 'edit', action=form_action, method='POST',
                        legend=self.model.name, children=childlist)
        return form_node

    def _grid(self, cursor):
        """build grid of results for index and match"""
        grid = []
        for item in self.model.find(cursor.equery, skip=cursor.skip, limit=cursor.limit):
            item_id = item['id']
            item_node = build_item(item, 'grid')
            #TODO: use one column to link to 'show' method
            delete = grid_button(self.name, 'delete', id=item_id, confirm='yes',
                                 prompt='delete {0} {1}'.format(self.name, item_id))
            modify = grid_button(self.name, 'modify', id=item_id)
            item_node['children'].insert(0, delete)
            item_node['children'].insert(0, modify)
            grid.append(item_node)
        return grid

    @action('List', 'list-alt', 'GET,POST', '/index')
    def index(self, req):
        """show index for item collection"""
        cursor = Cursor(self.model) if req.method == 'GET' else Cursor(self.model, req)
        #TODO: add_bottom_hook(delete_snippet)
        #TODO: handle case in which self._grid returns []
        grid_node = node('grid', '', children=self._grid(cursor))
        # build browse panel
        top_panel = node('panel', 'browse', children=[node('title', 'cursor',   content='Index '+self.name),
                                                      cursor.form(url_for(self.name, 'index'))])
        new = panel_button(self.name, 'new')
        bottom_panel = node('panel', 'normal', children=[new])
        return top_panel, grid_node, bottom_panel

    @action('Search', 'eye', 'POST', '/match')
    def match(self, req):
        """show result list of search in item collection"""
        cursor = Cursor(self.model, req)
        if not cursor.query:
            logger.debug('match: invalid query '+str(cursor.error))
            return self.search(req, cursor.error) # show search form and errors
        #TODO: $key $op $value, where $op is 'in' for 'text' and 'memo', otherwise 'eq'
        grid_node = node('grid', '', children=self._grid(cursor))
        logger.debug('match: valid query => {0} results'.format(len(grid_node['children'])))
        # build browse panel
        qs = ', '.join([key+'='+str(value) for key, value in cursor.query.items()])
        top_panel = node('panel', 'browse', children=[node('title', 'cursor',   content='Search '+self.name+': '+qs),
                                                      cursor.form(url_for(self.name, 'match'))])
        #TODO: add_bottom_hook(delete_snippet)
        new = panel_button(self.name, 'new')
        bottom_panel = node('panel', 'normal', children=[new])
        return top_panel, grid_node, bottom_panel

    def _modify(self, item, action, error={}):
        """build page content for create/update form, plus buttons"""
        ok         = form_button('OK',     'ok')
        cancel     = form_button('Cancel', 'times')
        panel_node = node('panel', 'form', children=[ok, cancel])
        childlist  = build_form(item, error=error)
        childlist.append(panel_node)
        #TODO: add_bottom_hook(edit_snippet)
        form_node = node('form', 'edit', action=action, method='PUT',
                         legend=self.model.name, children=childlist, next='')
        logger.debug('_modify: (re)post form')
        return form_node

    @action('Modify', 'pencil', 'GET', '/{id}/modify')
    def modify(self, req, **kwarg):
        """get form for modify/update action"""
        item_id = kwarg['id']
        item = self.model.lookup(item_id)
        form_action = url_for(self.name, 'update', id=item_id)
        return self._modify(item, form_action)

    @action('Create', 'plus', 'GET', '/new')
    def new(self, req):
        """get form for new/create action"""
        form_action = url_for(self.name, 'create')
        ok          = form_button('OK',     'ok')
        cancel      = form_button('Cancel', 'times')
        panel_node  = node('panel', 'form', children=[ok, cancel])
        childlist   = build_empty_form(self.model({}))
        childlist.append(panel_node)
        #TODO: add_bottom_hook(edit_snippet)
        form_node = node('form', 'edit', action=form_action, method='POST',
                        legend=self.model.name, children=childlist, next='')
        return form_node

    @action('Duplicate', 'tags', 'GET', '/{id}/clone')
    def clone(self, req, **kwarg):
        """get form for clone=modify/create action"""
        item_id     = kwarg['id']
        form_action = url_for(self.name, 'create')
        ok          = form_button('OK',     'ok')
        cancel      = form_button('Cancel', 'times')
        panel_node  = node('panel', 'form', children=[ok, cancel])
        item = self.model.lookup(item_id)
        childlist = build_form(item.copy())
        childlist.append(panel_node)
        #TODO: add_bottom_hook(edit_snippet)
        form_node = node('form', 'edit', action=form_action, method='POST',
                         legend=self.model.name, children=childlist, next='')
        return form_node

    def _update(self, req, item, action):
        """validate item content, save and confirm"""
        formdoc = self.model.convert(req.params)
        # update (empty) item with converted form contents
        for name, value in formdoc.items():
            item[name] = value
        result = item.validate(item)
        if result['ok']:
            item.write(validate=False)
            logger.debug('_update: validation OK, show item')
            nodes = self._show(item)  # show modified item
            return nodes
        else:
            logger.debug('_update: validation not OK, retry modification')
            return self._modify(item, action, result['error']) # show modified item and errors

    @action('OK', 'ok', 'PUT', '/{id}')
    def update(self, req, **kwarg):
        """update existing item"""
        item_id = kwarg['id']
        item = self.model.lookup(item_id)
        if req.params['$submit'] == 'OK':
            logger.debug('update: submit == OK')
            return self._update(req, item, url_for(self.name, 'update', id=item_id))
        else:
            logger.debug('update: submit == Cancel')
            return self._show(item) # show unmodified item

    @action('OK', 'ok', 'POST', '')
    def create(self, req):
        """create new item"""
        item = self.model({})
        if req.params['$submit'] == 'OK':
            self._update(req, item, url_for(self.name, 'create'))
        else:
            return self.index(req) # no unmodified item, show index

    @action('Delete', 'trash-o', 'DELETE', '/{id}')
    def delete(self, req, **kwarg):
        """delete one item"""
        item_id = kwarg['id']
        item = self.model.lookup(item_id)
        item['active'] = False # item.remove() should be used only during clean-up
        result = item.write()
        return node('block', '', ok=result['ok'], origin=req.referrer)

#TODO import: import one or more items
    # @action('Import', 'download', 'GET,POST', '/import')
    # def import(cls, filename):
    #     """
    #     import(self, filename): n
    #     Import documents from file.
    #     Return value if number of validated documents imported.
    #     """
    #     pass # import documents of this model from CSV file (form-based file upload)
