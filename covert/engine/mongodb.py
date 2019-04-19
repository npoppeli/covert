# -*- coding: utf-8 -*-
"""Objects and functions related to the MongoDB storage engine.

This module defines the Item class and an initialization function for the storage engine.
The Item class encapsulates the details of the storage engine.
"""

from datetime import datetime
from time import clock
from pymongo import MongoClient
from ..common import SUCCESS, ERROR, FAIL, logger, InternalError
from ..model import BareItem, mapdoc, Visitor, Filter
from .. import setting
from bson.objectid import ObjectId

def report_db_action(result):
    message = "{}: status={} data={} ".format(datetime.now(), result['status'], result['data'])
    if 'message' in result:
        message += result['message']
    if setting.debug > 1:
        logger.debug(message)

query_map = {
    '==': lambda x, y: x,
    'eq': lambda x, y: x,
    '=~': lambda x, y: {'$regex': x},
    're': lambda x, y: {'$regex': x},
    '[]': lambda x, y: {'$gte': x, '$lte': y},
    'in': lambda x, y: {'$gte': x, '$lte': y},
    '!=': lambda x, y: {'$ne': x},
    '<>': lambda x, y: {'$ne': x},
    '<' : lambda x, y: {'$lt': x},
    'lt': lambda x, y: {'$lt': x},
    '>' : lambda x, y: {'$gt': x},
    'gt': lambda x, y: {'$gt': x},
    '<=': lambda x, y: {'$lte': x},
    'le': lambda x, y: {'$lte': x},
    '>=': lambda x, y: {'$gte': x},
    'ge': lambda x, y: {'$gte': x}
}

class Translator(Visitor):
    """Translate query to form suitable for this storage engine.

    A filter is a sequence of terms or nested clauses (and, or). A term is a tuple (op, value) or
    (op, value1, value2), where 'op' is a 2-character string specifying a filter operator.
    The translation to MongoDB form is given by 'query_map'. Fields with 'multiple' property
    (list-valued fields) have a normal query condition, since MongoDB does not distinguish
    search scalar field from search list field.
    """
    def  __init__(self, wmap):
        self.wmap = wmap

    def visit_filter(self, node):
        result = {}
        for term in node.terms:
            result.update(self.visit(term))
        return result

    def visit_and(self, node):
        result = [self.visit(term) for term in node.terms]
        return {'$and': result}

    def visit_or(self, node):
        result = [self.visit(term) for term in node.terms]
        return {'$or': result}

    def visit_term(self, node):
        field = node.field
        operator = node.operator
        wmap = self.wmap
        value1 = wmap[field](node.value1) if (node.value1 and field in wmap) else node.value1
        value2 = wmap[field](node.value2) if (node.value2 and field in wmap) else node.value2
        if operator in query_map:
            result = {field: query_map[operator](value1, value2)}
        else:
            result = {field: {operator: value1}}
        return result

def init_storage():
    """Initialize storage engine."""
    setting.store_connection = MongoClient()
    setting.store_db = setting.store_connection[setting.store_dbname]
    if setting.debug >= 2:
        logger.debug("Create MongoDB connection, set database to '{}'".format(setting.store_dbname))

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
        coll_list = setting.store_db.collection_names()
        if cls.name not in coll_list:
            setting.store_db.create_collection(cls.name)

    @classmethod
    def create_index(cls, index_keys):
        """Create index on index_keys.

        Create index on index_keys, unless this index is already present.

        Arguments:
            index_keys (list): list of 2-tuples (name, direction), where direction is 1 or -1

        Returns:
            None
        """
        collection = setting.store_db[cls.name]
        for item in index_keys:
            collection.create_index(item[0], unique=False)

    @classmethod
    def filter(cls, obj):
        """Create filter from Filter object `obj`.

        In the view methods, filters are specified as instance of the Filter class.
        Fields with 'multiple' property (list-valued fields) have a normal query condition.

        Arguments:
            obj (Filter): Filter object.

        Returns:
            dict: filter in MongoDB form.
        """
        if obj is None:
            return None
        if setting.debug and not isinstance(obj, Filter):
            raise ValueError('Argument 2 of Item.filter not a Filter instance')
        translator = Translator(cls.wmap)
        return translator.visit(obj)

    @classmethod
    def max(cls, field):
        """Find maximum value in collection of field value.

        Go through all items in collection, and determine maximum value of 'field'.
        Arguments:
            field (str): field name

        Returns:
            any: maximum value.
        """
        cursor = setting.store_db[cls.name].find().sort([(field, -1)]).limit(1)
        return cursor[0][field]

    @classmethod
    def count(cls, fltr):
        """Count items in collection that match a given query.

        Find zero or more items (documents) in collection, and count them.

        Arguments:
            fltr (Filter): instance of Filter class

        Returns:
            int: number of matching items.
        """
        cursor = setting.store_db[cls.name].find(filter=cls.filter(fltr))
        return cursor.count()

    @classmethod
    def find(cls, fltr, skip=0, limit=0, sort=None):
        """Retrieve items from collection.

        Find zero or more items in collection, and return these in the
        form of a list of 'cls' instances. Assumption: stored items are valid.

        Arguments:
            fltr  (Filter): instance of Filter class
            skip  (int)   : number of items to skip.
            limit (int)   : maximum number of items to retrieve.
            sort  (list)  : sort specification.

        Returns:
            list: list of 'cls' instances.
        """
        sort_spec = sort if sort else [('_skey',1)]
        cursor = setting.store_db[cls.name].find(filter=cls.filter(fltr),
                                                 skip=skip, limit=limit, sort=sort_spec)
        return [cls(item) for item in cursor]

    @classmethod
    def project(cls, field, fltr, sort=None, bare=False):
        """Retrieve items from collection, and return selection of fields.

        Find zero or more items in collection, and return these in the
        form of a list of tuples. Assumption: stored items are valid.

        Arguments:
            fltr  (Filter)      : instance of Filter class
            field (string, list): name(s) of field(s) to include.
            sort  (list)        : sort specification.
            bare  (bool)        : if True, return only bare values.

        Returns:
            list: list of field values, tuples or dictionaries
        """
        mono = isinstance(field, str)
        sort_spec = sort if sort else [('_skey',1)]
        proj_spec = {field: 1} if mono else dict.fromkeys(field, 1)
        cursor = setting.store_db[cls.name].find(filter=cls.filter(fltr),
                                                 projection=proj_spec, sort=sort_spec)
        if bare:
            if mono:
                return [doc[field] for doc in cursor]
            else:
                return [tuple(doc[f] for f in field) for doc in cursor]
        else:
            return list(cursor)

    @classmethod
    def lookup(cls, oid):
        """Retrieve one item from collection.

        Retrieve first item in collection matching the given primary key (id),
        or None if no item matches this key.

        Arguments:
           oid (str): value of 'id' attribute.

        Returns:
            'cls' instance
        """
        item = setting.store_db[cls.name].find_one({'id':oid})
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
        item = setting.store_db[cls.name].find_one(cls.filter(doc))
        if item is None:
            return item
        else:
            return cls(item)

    def finalize(self):
        """Finalize item before writing to permanent storage.

        Finalization includes setting of auto fields.
        NOTE: if you want to skip this step, at least update self['mtime'], e.g.
        +timedelta(hours=1) to avoid writing an item with duplicate id to the database.

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

    def notify(self):
        """Notify other items that the present item has been modified.
        NOTE: this should be used with care, avoiding cycles, infinite recursion etcetera.

        Returns:
            None
        """
        pass

    def write(self, validate=True):
        """Write item to permanent storage.

        Save item (document) contained in this instance.

        Arguments:
            validate (bool): if True, validate this item before writing.

        Returns:
            dict: {'status':SUCCESS, 'data':<item id>} or
                  {'status':FAIL, 'data':None}.
        """
        self.finalize()
        new = self['mtime'] == self['ctime']
        if validate:
            validate_result = self.validate(self)
            if validate_result['status'] != SUCCESS:
                message = "{} {}\ndoes not validate because of error\n{}\n".\
                    format(self.name, self, validate_result['data'])
                result = {'status':FAIL, 'data':message}
                report_db_action(result)
                return result
        doc = {key: value for key, value in mapdoc(self.wmap, self).items()
                          if not key.startswith('__')}
        collection = setting.store_db[self.name]
        if setting.nostore: # don't write to the database
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
            self.notify()
            return reply
        except Exception as e:
            message = 'item {}\nnot written because of error\n{}\n'.format(doc, str(e))
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
        collection = setting.store_db[self.name]
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
                message = 'item {}\nnot updated, matched count={}'.format(self, result.matched_count)
                raise InternalError(message)
            return reply
        except Exception as e:
            message = 'item {}\nnot updated because of error\n{}\n'.format(self, str(e))
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
        collection = setting.store_db[self.name]
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
                message = 'item {}\nnot updated, matched count={}'.format(self, result.matched_count)
                raise InternalError(message)
            return reply
        except Exception as e:
            message = 'item {}\nnot written because of error\n{}\n'.format(self, str(e))
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
        collection = setting.store_db[self.name]
        result = collection.delete_one({'_id':item_id})
        reply = {'status':SUCCESS if result.deleted_count == 1 else FAIL, 'data': item_id}
        report_db_action(reply)
        return reply
