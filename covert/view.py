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

def normal_button(view_name, route_name, item):
    # TODO: add enabled
    return {'label': label_for(route_name), 'icon': icon_for(route_name),
            'action': url_for(view_name, route_name, item), 'method':'GET'}

def form_button(view_name, route_name, item):
    return {'label': label_for(route_name), 'icon': icon_for(route_name),
            'action': url_for(view_name, route_name, item), 'method':'POST'}

def delete_button(view_name, route_name, item):
    # TODO: add enabled; add data-prompt (Bootstrap JS)
    return {'label': label_for(route_name), 'icon': icon_for(route_name),
            'action': url_for(view_name, route_name, item), 'method':'DELETE'}

class BareItemView:
    """
    BareItemView: bare view that does not define routes. It serves as superclass for
    ItemView and for view classes that define their own specific routes.
    """
    model = 'BareItem'
    prefix = ''
    def __init__(self, request, matches):
        self.request = request
        self.params = matches

class ItemView(BareItemView):
    """
    ItemView: superclass for views that implement the Atom Publishing protocol
    (create, index, new, update, delete, edit, show) plus extensions.
    """
    model = 'Item'

    def tree_with_item(self, oid, buttons):
        item = self.model.lookup(oid)
        fields = item.mfields
        button_list = [normal_button(self.prefix, button, item) for button in buttons]
        labels = dict([(field, item.skeleton[field].label) for field in fields])
        # add fields and labels TODO: add icons and any other UI information
        return {'content': {'item':item.display(), 'buttons':button_list},
                'fields': fields, 'labels': labels}

    def tree_with_cursor(self):
        numbers = ('skip', 'limit', 'count', 'incl', 'incl0', 'dir')
        cursor = {'skip':0, 'limit':10, 'count':0, 'incl':0, 'incl0':0, 'dir':0}
        query = {}
        for key, value in self.request.params.items():
            if key.startswith('_'):
                newkey = key[1:]
                cursor[newkey] = str2int(value) if newkey in numbers else value
            elif value:
                query[key] = value
        if query: # follow-up post
            cursor['query'] = decode_dict(query)
        else: # initial post
            valid = self.model.validate(query, 'query')
            if valid['ok']:
                cursor['query'] = query
                feedback = ''
            else:
                cursor['query'] = {}
                feedback = valid['error']
        # full query = user query + condition depending on 'incl'
        full_query = {'active': ''} if cursor['incl'] == 1 else {}
        full_query.update(query)
        if cursor['count'] == 0 or cursor['incl'] != cursor['incl0']:
            # not counted before or the 'inclusive' has changed
            cursor['count'] = self.model.count(full_query)
        cursor['skip'] = max(0, min(cursor['count'],
                                    cursor['skip'] + cursor['dir'] * cursor['limit']))
        cursor['incl0'] = cursor['incl']
        cursor['prev'] = cursor['skip']>0
        cursor['next'] = cursor['skip']+cursor['limit'] < cursor['count']
        return {'cursor':cursor, 'feedback':feedback, 'content':[]}

    @route('/{id:objectid}', template='show')
    def show(self):
        """display one item"""
        t1 = self.tree_with_item(self.params['id'], ['index', 'update', 'delete'])
        # TODO: delete button requires prompt and JS
        return t1

    @route('/index', template='index')
    def index(self):
        """display multiple items (collection)"""
        t1 = self.tree_with_cursor() # TODO: add 'new' button at collection level
        if t1['feedback']:
            return t1
        items = self.model.find({}, limit=r1['cursor']['limit'], skip=r1['cursor']['skip'])
        if not items:
            t1['feedback'] = 'Nothing found'
            return t1
        item0 = items[0]
        t1['buttons'] = [normal_button('new',  url_for(self.prefix, 'new',  item0))]
        t2 = self.add_content(items) # also add 'fields': item0.sfields
        for item in r1:
            buttons = [normal_button(self.prefix, 'modify', item),
                       normal_button(self.prefix, 'delete', item)]
            itemlist.append({'item':item.display(), 'buttons':buttons})
            # TODO: change field 0 into tuple (label, url)
            # where url=url_for(self.prefix, 'show',   item)
        return t2

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
        r1 = self.tree_with_item(self.params['id'], [])
        r2 = self.add_form_buttons(r1, ['ok', 'cancel'])
        return r2

    @route('/{id:objectid}', method='PUT', template='update')
    def update(self): # update person
        # TODO: update if 'OK' was clicked, else use unmodified item
        r1 = self.model.update({'id':self.params['id']}, form2update(self.request))
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
