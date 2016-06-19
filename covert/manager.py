# -*- coding: utf-8 -*-
"""
covert.manager
-----
Objects and functions related to managing items in storage.
"""

import imp, re
from .common import Error
from .model import BareItem
from .report import logger
from . import setting

def register_manager(manager):
    assert isinstance(manager, ItemMgr)
    assert manager.model.__name__ in setting.model_map
    setting.action_map.extend(manager._action)

def import_managers(name):
    """import Python module with ItemMgr sub-classes"""
    # valid for Python 3.1-3.3; as of 3.4 we should use importlib.import_module
    try:
        (fileobj, path, details) = imp.find_module(name, [setting.sitedir])
        module = imp.load_module(setting.sitedir, fileobj, path, details)
    except ImportError:
        logger.debug("Could not import {}.py from {}".format(name, setting.sitedir))

# ItemMgr class, and decorator used for the view methods
class action:
    """
    action: decorator for methods in an ItemMgr class. This adds attributes to methods.
    Once set, these attributes cannot be changed anymore.
    @action(method, pattern)
    - method: string identifying HTTP method (e.g. 'GET' or 'GET, POST')
    - pattern: URL pattern, given as a format string
    """
    def __init__(self, method, pattern):
        self.method = method; self.pattern = pattern
    def __call__(self, wrapped):
        wrapped.method = self.method; wrapped.pattern = self.pattern
        return wrapped

class ItemView:
    """
    ItemView: class for manager objects that implement the Atom Publishing protocol.
    Decorated methods are called 'actions'.
    """
    model = BareItem
    def __init__(self):
        name = self.__class__.__name__
        # manager classes must have a name that ends in 'Mgr'
        if len(name) > 5 and name[-5:] == 'Mgr':
            self._action = []
            self.name = name.replace('Mgr', '', 1).lower()
            for name in dir(self):
                member = getattr(self, name)
                if hasattr(member, 'pattern'): # decorated method, i.e. an action
                    pattern = '^' + member.pattern + '$'
                    regex = pattern.replace('{id}',   r'(?P<id>\w+)').\
                                    replace('{path}', r'(?P<path>.+)')
                self._action.append((member.method, re.compile(regex), member))
            # sorting in reverse alphabetical order avoid mismatches in PatternRouter
            self._action.sort(key=lambda action: action[0].pattern, reverse=True)
        else:
            raise Error("ItemMgr sub-class {} has incorrect name".format(name))

    @action('GET',    '', 'item_read_more')
    def read_coll(self, req, **kwarg):
        """get multiple items (item collection)"""
        result = self.model.find(qdoc={}, skip=0, limit=20)
        return result

    @action('GET',    '/{id}', 'item_read_one')
    def read_item(self, req, **kwarg):
        """get one item"""
        item = self.model.lookup(kwarg['id'])
        return {} if item == None else item

    @action('PUT',    '/{id}', 'item_update')
    def update_item(self, req, **kwarg):
        """validate item content, save and confirm"""
        formdoc = self.model.convert(self, req.params)
        # update item with converted form contents
        for name, value in formdoc.items():
            item[name] = value
        result = item.write(validate=False)
        return {'ok': result['ok']}

    @action('POST',   '')
    def create_item(self, req, **kwarg):
        pass

    @action('DELETE', '/{id}')
    def delete_item(self, req, **kwarg):
        """delete one item"""
        item_id = kwarg['id']
        item = self.model.lookup(item_id)
        item['active'] = False # item.remove() should be used only during clean-up
        result = item.write()
        return {'ok': result['ok']}

#TODO import: import one or more items
# @action('POST', '/import')
# def import(cls, filename):
#     """
#     import(filename): n
#     Import documents from file.
#     Return value if number of validated documents imported.
#     """
#     pass # import documents of this model from CSV file (form-based file upload)

class ExtItemMgr(ItemMgr):
    @action('GET',    '/{id}/{path}')
    def read_subcoll(self, req, **kwarg):
        """get multiple sub-items (embedded collection)
           Example: /journal/12345678/volume, /journal/12345678/volume/8/issue"""
        item = self.model.lookup(kwarg['id'])
        path = '/'.split(kwarg['path'])
        if item == None or len(path) % 2 == 0: # path should have odd number of components
            return []
        else:
            # descend into /journal/12345678, return  array 'volume', or
            # descend into /journal/12345678/volume/8, return array 'issue'
            current = item
            while len(path) > 2:
                name = path.pop[0]; index = path.pop[1]
                current = current[name][index]
            #TODO: limit to 20
            return current[path[0]]

    @action('GET',    '/{id}/{path}', 'item_read_subitem')
    def read_subitem(self, req, **kwarg):
        """get one sub-item
           Example: /journal/12345678/volume/8, /journal/12345678/volume/8/issue/1"""
        item = self.model.lookup(kwarg['id'])
        return {} if item == None else item

    @action('PUT',    '/{id}/{path}')
    def update_subitem(self, req, **kwarg):
        """update existing item"""
        item_id = kwarg['id']
        item = self.model.lookup(item_id)
        if req.params['$submit'] == 'OK':
            logger.debug('update: submit == OK')
            return self._update(self, req, item, url_for(self.name, 'update', id=item_id))
        else:
            logger.debug('update: submit == Cancel')
            return self._show(item) # show unmodified item

    @action('POST',   '{id}/{path}')
    def create_subitem(self, req, **kwarg):
        """create new item"""
        item = self.model({})
        if req.params['$submit'] == 'OK':
            self._update(self, req, item, url_for(self.name, 'create'))
        else:
            return self.index(self, req) # no unmodified item, show index

    @action('DELETE', '/{id}/{path}')
    def delete_subitem(self, req, **kwarg):
        pass
