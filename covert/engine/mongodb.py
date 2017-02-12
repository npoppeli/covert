# -*- coding: utf-8 -*-
"""Objects and functions related to the MongoDB storage engine.

This module defines the Item class and an initialization function for the storage engine.
The Item class encapsulates the details of the storage engine.
"""

from datetime import datetime
from pymongo import MongoClient
from ..common import SUCCESS, ERROR, FAIL, logger, InternalError
from ..model import BareItem, mapdoc
from .. import setting
from bson.objectid import ObjectId

query_map = {
    '==': lambda t: t[1],
    '=~': lambda t: {'$regex':t[1]},
    '[]': lambda t: {'$gte': t[1], '$lte': t[2]},
    '<=': lambda t: {'$lte': t[1]},
    '>=': lambda t: {'$gte': t[1]}
}

def report_db_action(result):
    logger.debug("{}: status={} data={}".format(datetime.now(), result['status'], result['data']))
    if 'message' in result:
        logger.debug(result['message'])

def translate_query(query):
    """Translate query to form suitable for this storage engine.

    In the view methods, queries are specified as sequences of tuples (op, value) or (op, value1,
    value2) where 'op' is a 2-character string specifying a search operator, and 'value' is a
    value used in the search. The translation to MongoDB form is given by 'query_map'.
    """
    result = {}
    for key, value in query.items():
        operator = value[0]
        if operator in query_map:  # apply mapping function
            if isinstance(value, dict):  # embedded document
                result[key] = mapdoc(query_map, value)
            else:  # scalar
                result[key] = query_map[operator](value)
        else:  # no mapping for this element
            result[key] = value
    return result

def init_storage():
    """Initialize storage engine."""
    logger.debug('Creating MongoDB connection')
    setting.store_connection = MongoClient()
    logger.debug("Setting MongoDB database to '{}'".format(setting.store_dbname))
    setting.store_db = setting.store_connection[setting.store_dbname]

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
        collection.ensure_index(index_keys, unique=False)

    @classmethod
    def query(cls, doc):
        """Create query.

        Create query from dictionary doc.

        Arguments:
            doc (dict): dictionary specifying a search query.

        Returns:
            dict: query in MongoDB form.
        """
        return translate_query(doc)

    @classmethod
    def count(cls, doc):
        """Count items in collection that match a given query.

        Find zero or more items (documents) in collection, and count them.
        Arguments:
            doc (dict): dictionary specifying the query, e.g. {'id': ('==', '1234')}

        Returns:
            int: number of matching items.
        """
        cursor = setting.store_db[cls.name].find(filter=cls.query(doc))
        return cursor.count()

    @classmethod
    def find(cls, doc, skip=0, limit=0, sort=None):
        """Retrieve items from collection.

        Find zero or more items in collection, and return these in the
        form of a list of 'cls' instances. Assumption: stored items are valid.
        Arguments:
            doc   (dict): dictionary specifying the query, e.g. {'id': ('==', '1234')}.
            skip  (int):  number of items to skip.
            limit (int):  maximum number of items to retrieve.
            sort  (list): sort specification.

        Returns:
            list: list of 'cls' instances.
        """
        cursor = setting.store_db[cls.name].find(filter=cls.query(doc),
                                                 skip=skip, limit=limit, sort=sort)
        return [cls(item) for item in cursor]

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
        item = setting.store_db[cls.name].find_one(cls.query(doc))
        if item is None:
            return item
        else:
            return cls(item)

    def finalize(self):
        """Finalize item before writing to permanent storage.

        Finalization includes setting of auto fields.

        Returns:
            None
        """
        new = self.get('id', '') == ''
        self['mtime'] = datetime.now()
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
                reply= {'status':SUCCESS, 'data':str(result.inserted_id)}
            else:
                result = collection.replace_one({'_id':self['_id']}, doc)
                reply = {'status':SUCCESS, 'data':self['id'], 'message':str(result.raw_result)}
            report_db_action(reply)
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
