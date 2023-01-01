# -*- coding: utf-8 -*-
"""Objects and functions related to the MongoDB storage engine.

This module defines the Item class and an initialization function for the storage engine.
The Item class encapsulates the details of the storage engine.
"""

import ast
from datetime import datetime
from pymongo import MongoClient
from ..common import SUCCESS, ERROR, FAIL, logger, InternalError
from .. import common as c
from ..event import event
from ..model import BareItem, mapdoc
from .. import setting
from bson.objectid import ObjectId

def report_db_action(result):
    message = "{}: status={} data={} ".format(datetime.now(), result['status'], result['data'])
    if 'message' in result:
        message += result['message']
    if setting.debug > 1:
        logger.debug(message)
    elif result['status'] != SUCCESS:
        logger.info(c._('Item could not be written: ') + message)

class Translator(ast.NodeVisitor):
    """Instances of this class translate a filter in the form of a compiled
    Python expression to a dictionary with a MongoDB query specification.

    A filter is a restricted form of Python expression.
    Field names are written as variables. Constants are always strings.
    Allowed boolean operators: and, not.
    Allowed binary operators: ==, ~=, <, <=, >, >=, in, % (match regex).
    Fields with 'multiple' property (list-valued fields) have a normal query condition,
    since MongoDB does not distinguish search scalar field from search list field.
    """
    def  __init__(self, cmap, wmap):
        self.cmap = cmap
        self.wmap = wmap

    def V_(self, key, value):
        """Convert string value to real value for database query: wmap(cmap(value))"""
        v1 = self.cmap[key](value) if value and (key in self.cmap) else value
        v2 = self.wmap[key](v1) if v1 and (key in self.wmap) else v1
        return v2

    # default method
    def generic_visit(self, n):
        raise NotImplementedError(c._('Translator: no method for ')+n.__class__.__name__)
    # auxiliaries
    def visit_elts        (self, n): return [self.visit(elt) for elt in n.elts]
    def visit_keys        (self, n): return [self.visit(elt) for elt in n.keys]
    def visit_values      (self, n): return [self.visit(elt) for elt in n.values]
    # simple nodes
    def visit_And         (self, n): return '$and'
    def visit_Eq          (self, n): return '$eq'
    def visit_NotEq       (self, n): return '$ne'
    def visit_Lt          (self, n): return '$lt'
    def visit_LtE         (self, n): return '$lte'
    def visit_Gt          (self, n): return '$gt'
    def visit_GtE         (self, n): return '$gte'
    def visit_Expr        (self, n): return self.visit(n.value)
    def visit_In          (self, n): return '$in'
    def visit_Mod         (self, n): return '$regex'
    def visit_Name        (self, n): return n.id
    def visit_NameConstant(self, n): return n.value
    def visit_Num         (self, n): return n.n
    def visit_Or          (self, n): return '$or'
    def visit_Str         (self, n): return n.s
    def visit_List        (self, n): return self.visit_elts(n)
    def visit_Tuple       (self, n): return self.visit_elts(n)
    # complex nodes
    def visit_Attribute(self, n):
        return '{}.{}'.format(self.visit(n.value), n.attr)
    def visit_Dict(self, n):
        return dict(zip(self.visit_keys(n), self.visit_values(n)))
    def visit_BinOp(self, n):
        key, value = self.visit(n.left), self.visit(n.right)
        return {key: {self.visit(n.op): self.V_(key, value)}}
    def visit_BoolOp(self, n):
        return {self.visit(n.op): self.visit_values(n)}
    def visit_Compare(self, n):
        key, operator = self.visit(n.left), self.visit(n.ops[0])
        if operator == '$in':
            value1, value2 = self.visit(n.comparators[0])
            return {key: {'$gte': self.V_(key, value1), '$lte': self.V_(key, value2)}}
        else:
            value1 = self.visit(n.comparators[0])
            if isinstance(value1, dict):
                return {key+'.'+k: self.V_(k, v) for k, v in value1.items()}
            else:
                return {key: {operator: self.V_(key, value1)}}

def init_storage():
    """Initialize storage engine."""
    setting.connection = MongoClient()
    dbname = setting.dbname
    setting.item_db = setting.connection[dbname]
    if setting.debug >= 2:
        logger.debug(c._("Create MongoDB connection, set database to '{}'").format(dbname))

class Item(BareItem):
    """Class for reading and writing objects from/to this storage engine.

    This class adds storage-dependent methods to the base class BareItem.
    """
    @classmethod
    def create_collection(cls):
        """Create collection cls.name, unless this is already present.

        Returns:
            None
        """
        coll_list = setting.item_db.list_collection_names()
        if cls.name not in coll_list:
            setting.item_db.create_collection(cls.name)

    @classmethod
    def create_index(cls, index_keys):
        """Create index on index_keys.

        Create index on index_keys, unless this index is already present.

        Arguments:
            index_keys (list): list of 2-tuples (name, direction), where direction is 1 or -1

        Returns:
            None
        """
        collection = setting.item_db[cls.name]
        for index_tuple in index_keys:
            collection.create_index(index_tuple[0])

    @classmethod
    def filter(cls, expr):
        """Create filter from filter expression `expr`.

        In the view methods, filters are specified as Python expressions.
        Fields with 'multiple' property (list-valued fields) have a normal query condition.

        Arguments:
            expr (str): Python expression.

        Returns:
            dict: query document in MongoDB form.
        """
        if not expr:
            return {}
        try:
            root = compile(expr, '', 'eval', ast.PyCF_ONLY_AST)
        except SyntaxError as e:
            logger.info(c._("Item.filter: expr = {}").format(expr))
            logger.info(c._("Exception '{}'").format(e))
            raise
        translator = Translator(cls.cmap, cls.wmap)
        try:
            result = translator.visit(root.body)
            return result
        except Exception as e:
            logger.info(str(e))
            logger.info(c._("Item.filter: expr = {}").format(expr))
            logger.info(c._("Item.filter: root = {}").format(ast.dump(root)))
            return {}

    @classmethod
    def max(cls, field):
        """Find maximum value in collection of field value.

        Go through all items in collection, and determine maximum value of 'field'.
        Arguments:
            field (str): field name

        Returns:
            any: maximum value.
        """
        cursor = setting.item_db[cls.name].find().sort([(field, -1)]).limit(1)
        return cursor[0][field]

    @classmethod
    def count(cls, expr=''):
        """Count items in collection that match a given query.

        Find zero or more items (documents) in collection, and count them.

        Arguments:
            expr (str): Python expression.

        Returns:
            int: number of matching items.
        """
        return setting.item_db[cls.name].count_documents(filter=cls.filter(expr))

    @classmethod
    def find(cls, expr=None, skip=0, limit=0, sort=None):
        """Retrieve items from collection.

        Find zero or more items in collection, and return these in the
        form of a list of 'cls' instances. Assumption: stored items are valid.

        Arguments:
            expr  (str) : Python expression.
            skip  (int) : number of items to skip.
            limit (int) : maximum number of items to retrieve.
            sort  (list): sort specification.

        Returns:
            list: list of 'cls' instances.
        """
        sort_spec = sort if sort else [('_skey',1)]
        cursor = setting.item_db[cls.name].find(filter=cls.filter(expr),
                                                skip=skip, limit=limit, sort=sort_spec)
        return [cls(item) for item in cursor]

    @classmethod
    def project(cls, field, expr, sort=None, limit=0, bare=False):
        """Retrieve items from collection, and return selection of fields.

        Find zero or more items in collection, and return these in the
        form of a list of tuples. Assumption: stored items are valid.

        Arguments:
            expr  (str)         : Python expression.
            field (string, list): name(s) of field(s) to include.
            sort  (list)        : sort specification.
            limit (int)         : maximum number of items to retrieve.
            bare  (bool)        : if True, return only bare values.

        Returns:
            list: list of field values, tuples or dictionaries
        """
        mono = isinstance(field, str)
        sort_spec = sort if sort else [('_skey',1)]
        proj_spec = {field: 1} if mono else dict.fromkeys(field, 1)
        cursor = setting.item_db[cls.name].find(filter=cls.filter(expr), limit=limit,
                                                projection=proj_spec, sort=sort_spec)
        if bare:
            if mono:
                return [doc[field] for doc in cursor]
            else:
                return [tuple(doc[f] for f in field) for doc in cursor]
        else:
            return list(cursor)

    @classmethod
    def lookup(cls, oid, key='id'):
        """Retrieve one item from collection.

        Retrieve first item in collection matching the given uniquely
        identifying key (preferably 'id'), or None if no item matches this key.

        Arguments:
           key (str): name of uniquely identifying attribute.
           oid (str): value of this attribute.

        Returns:
            'cls' instance
        """
        item = setting.item_db[cls.name].find_one({key:oid})
        if item is None:
            return item
        else:
            return cls(item)

    @classmethod
    def read(cls, doc):
        """Retrieve one item from collection.

        Retrieve first item in collection matching the given query (doc),
        or None if no item matches this key.

        Arguments:
           doc (dict): search query.

        Returns:
            'cls' instance.
        """
        item = setting.item_db[cls.name].find_one(cls.filter(doc))
        if item is None:
            return item
        else:
            return cls(item)

    def _finalize(self):
        """Finalize item before writing to permanent storage.

        Finalization includes setting of auto fields.

        Returns:
            None
        """
        new = self.get('id', '') == ''
        self['mtime'] = datetime.now()
        self['_skey'] = str(self['mtime'])
        if new:
            self['_id'] = ObjectId()
            self['id'] = str(self['_id'])
            self['active'] = True
            self['ctime'] = self['mtime']

    def write(self, validate=True):
        """Write item to permanent storage.

        Save item (document) contained in this instance.

        Arguments:
            validate (bool): if True, validate this item before writing.

        Returns:
            dict: {'status':SUCCESS, 'data':<item id>} or
                  {'status':FAIL, 'data':None}.
        """
        self._finalize()
        event('write:pre', self)
        new = self['mtime'] == self['ctime']
        if validate:
            validate_result = self.validate(self)
            if validate_result['status'] != SUCCESS:
                message = c._("{} {}\ndoes not validate because of error\n{}\n").\
                    format(self.name, self, validate_result['data'])
                result = {'status':FAIL, 'data':message}
                report_db_action(result)
                return result
        doc = {key: value for key, value in mapdoc(self.wmap, self).items()
                          if not key.startswith('__')}
        collection = setting.item_db[self.name]
        if setting.nostore: # do not write anything to the database
            reply = {'status':SUCCESS, 'data':'simulate '+('insert' if new else 'update')}
            report_db_action(reply)
            return reply
        try:
            if new:
                result = collection.insert_one(doc)
                message = 'nInserted=1'
                reply= {'status':SUCCESS, 'data':str(result.inserted_id), 'message':message}
            else:
                result = collection.replace_one({'_id':self['_id']}, doc)
                message = 'nModified=1'
                reply = {'status':SUCCESS, 'data':self['id'], 'message':message}
            report_db_action(reply)
            # This event handler can be used to notify other items that the present item has
            # been modified. Use this with care, and avoid infinite recursion caused by
            # event handlers indirectly calling each other!
            event('write:post', self)
            return reply
        except Exception as e:
            message = c._('{} {}\nnot written because of error\n{}\n').format(self.name, doc, str(e))
            reply = {'status':ERROR, 'data':None, 'message':message}
            report_db_action(reply)
            raise InternalError(message)

    # methods to set references (update database directly)
    def set_field(self, key, value):
        """Set one field in item to new value, directly in database.

        Arguments:
           key   (str):    name of field.
           value (object): value of field.

        Returns:
            dict: {'status':SUCCESS, 'data':<item id>} or
                  {'status':FAIL, 'data':None}.
        """
        item_id = self['_id']
        collection = setting.item_db[self.name]
        if setting.nostore: # don't write to the database
            reply = {'status': SUCCESS, 'data': 'simulate update'}
            report_db_action(reply)
            return reply
        doc = mapdoc(self.wmap, {key:value})
        try:
            result = collection.update_one({'_id':item_id}, {'$set':{key:doc[key]}})
            reply = {'status':SUCCESS if result.matched_count == 1 else FAIL,
                     'data': item_id, 'message':str(result.raw_result)}
            report_db_action(reply)
            if reply['status'] == FAIL:
                message = c._('{} {}\nnot updated, matched count={}').format(self.name, self, result.matched_count)
                raise InternalError(message)
            return reply
        except Exception as e:
            message = c._('{} {}\nnot updated because of error\n{}\n').format(self.name, self, str(e))
            reply = {'status':ERROR, 'data':None, 'message':message}
            report_db_action(reply)
            raise InternalError(message)

    def append_field(self, key, value):
        """Append value to list-valued field in item, directly in database.

        Arguments:
           key   (str):    name of (list-valued) field.
           value (object): additional value of field.

        Returns:
            dict: {'status':SUCCESS, 'data':<item id>} or
                  {'status':FAIL, 'data':None}.
        """
        item_id = self['_id']
        collection = setting.item_db[self.name]
        if setting.nostore: # don't write to the database
            reply = {'status': SUCCESS, 'data': 'simulate update'}
            report_db_action(reply)
            return reply
        doc = mapdoc(self.wmap, {key:value})
        try:
            result = collection.update_one({'_id':item_id}, {'$addToSet':{key:doc[key]}})
            reply = {'status':SUCCESS if result.matched_count == 1 else FAIL,
                     'data': item_id, 'message':str(result.raw_result)}
            report_db_action(reply)
            if reply['status'] == FAIL:
                message = c._('{} {}\nnot updated, matched count={}').format(self.name, self, result.matched_count)
                raise InternalError(message)
            return reply
        except Exception as e:
            message = c._('{} {}\nnot written because of error\n{}\n').format(self.name, self, str(e))
            reply = {'status':ERROR, 'data':None, 'message':message}
            report_db_action(reply)
            raise InternalError(message)

    def remove(self):
        """Remove item from collection (permanently).

        Remove item from collection.

        Returns:
            dict: {'status':SUCCESS, 'data':<item id>} or
                  {'status':FAIL, 'data':None}.
        """
        item_id = self['_id']
        collection = setting.item_db[self.name]
        result = collection.delete_one({'_id':item_id})
        reply = {'status':SUCCESS if result.deleted_count == 1 else FAIL, 'data': item_id}
        report_db_action(reply)
        return reply
