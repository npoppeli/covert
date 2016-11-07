# -*- coding: utf-8 -*-
"""Objects and functions related to the MongoDB storage engine.

This module defines the Item class and an initialization function for the storage engine.
The Item class encapsulates the details of the storage engine.

Todo:
    * make database connection thread-safe
    * text index via Collection.ensureIndex({'author': 'text', 'content': 'text'})
"""

from datetime import datetime
from pymongo import MongoClient
from ..common import SUCCESS, ERROR, FAIL, show_dict
from ..model import BareItem, mapdoc
from .. import setting
from bson.objectid import ObjectId

query_map = {
    '==': lambda t: t[1],
    '=~': lambda t: {'$regex':t[1]},
    '[]': lambda t: {'$gte':t[1], '$lte':t[2]}
}

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
    if setting.debug:
        print('Creating MongoDB connection')
    setting.store_connection = MongoClient()
    if setting.debug:
        print('Setting MongoDB database to', setting.store_dbname)
    setting.store_db = setting.store_connection[setting.store_dbname]

class Item(BareItem):
    """Class for reading and writing objects from/to this storage engine.

    This class adds storage-dependent methods to the base class BareItem.
    """
    @classmethod
    def create_collection(cls):
        """Create collection cls.name, unless this is already present.

        Returns:
            return value of Database.create_collection()
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
            return value of Collection.ensure_index()
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
            doc (dict): dictionary specifying the query, e.g. {'id': '1234'}

        Returns:
            int: number of matchhing items.
        """
        sequence = setting.store_db[cls.name].find(filter=cls.query(doc))
        return sequence.count()

    @classmethod
    def find(cls, doc, skip=0, limit=0, sort=None):
        """Retrieve items from collection.

        Find zero or more items in collection, and return these in the
        form of a list of 'cls' instances. Assumption: stored documents are valid.
        Arguments:
            doc   (dict): dictionary specifying the query, e.g. {'id': '1234'}.
            skip  (int):  number of items to skip.
            limit (int):  maximum number of items to retrieve.
            sort  (list): sort specification.

        Returns:
            list: list of 'cls' instances.
        """
        sequence = setting.store_db[cls.name].find(filter=cls.query(doc),
                                                   skip=skip, limit=limit, sort=sort)
        return [cls(item) for item in sequence]

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
        return cls(item)

    def write(self, validate=True):
        """Write document to permanent storage.

        Save document contained in this instance.

        Arguments:
            validate (bool): if True, validate this document before writing.

        Returns:
            dict: 'status':SUCCESS, 'id':<document id>} or {'status':FAIL, 'id':None}.
        """
        new = self.get('id', '') == ''
        self['mtime'] = datetime.now()
        if new:
            self['_id'] = ObjectId()
            self['id'] = str(self['_id'])
            self['active'] = True
            self['ctime'] = self['mtime']
        if validate:
            validate_result = self.validate(self)
            if validate_result['status'] != SUCCESS:
                message = "document {}\ndoes not validate because of error\n{}\n".\
                    format(self, validate_result['data'])
                return {'status':FAIL, 'data':message}
        try:
            doc = mapdoc(self.wmap, self)
            collection = setting.store_db[self.name]
            if new:
                result = collection.insert_one(doc)
                return {'status':SUCCESS, 'id':str(result.inserted_id)}
            else:
                result = collection.replace_one({'_id':self['_id']}, doc)
                return {'status':SUCCESS, 'id':str(result.upserted_id)}
        except Exception as e:
            message = 'document {}\nnot written because of error\n{}\n'.format(doc, str(e))
            return {'status':ERROR, 'id':None, 'message':message}

    # methods to set references (update database directly)
    def set_field(self, key, value):
        """Set one field in item to new value, directly in database.

        Arguments:
           key   (str):    name of field.
           value (object): value of field.

        Returns:
            dict: 'status':SUCCESS, 'id':<document id>} or {'status':FAIL, 'id':None}.
        """
        oid = self['id']
        collection = setting.store_db[self.name]
        result = collection.update_one({'id':oid}, {'$set':{key:value}})
        return {'status':SUCCESS if result.modified_count == 1 else FAIL, 'id': self['id']}

    def append_field(self, key, value):
        """Append value to list-valed field in item, directly in database.

        Arguments:
           key   (str):    name of (list-valued) field.
           value (object): additional value of field.

        Returns:
            dict: 'status':SUCCESS, 'id':<document id>} or {'status':FAIL, 'id':None}.
        """
        oid = self['id']
        collection = setting.store_db[self.name]
        result = collection.update_one({'_id':oid}, {'$addToSet':{key:value}})
        return {'status':SUCCESS if result.modified_count == 1 else FAIL, 'id': self['id']}

    def remove(self):
        """Remove item from collection (permanently).

        Remove item from collection.

        Returns:
        Returns:
            dict: 'status':SUCCESS, 'id':<document id>} or {'status':FAIL, 'id':None}.
        """
        oid = self['_id']
        collection = setting.store_db[self.name]
        result = collection.delete_one({'_id':oid})
        return {'status':SUCCESS if result.deleted_count == 1 else FAIL, 'id': self['id']}
