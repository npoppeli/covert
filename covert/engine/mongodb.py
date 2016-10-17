# -*- coding: utf-8 -*-
"""
covert.engine.mongodb
-----
Objects and functions related to the MongoDB storage engine.
"""

from datetime import datetime
from pymongo import MongoClient
from ..common import SUCCESS, ERROR, FAIL
from ..model import BareItem, mapdoc
from .. import setting
from bson.objectid import ObjectId

query_map = {
    '==': lambda t: t[1],
    '=~': lambda t: {'$regex':t[1]},
    '[]': lambda t: {'$gte':t[1], '$lte':t[2]}
}

def translate_query(query):
    """translate_query(query) -> result
       Translate query to a form suitable for this storage engine.
    """
    result = {}
    for key, value in query.items():
        operator =value[0]
        if operator in query_map:  # apply mapping function
            if isinstance(value, dict):  # embedded document
                result[key] = mapdoc(query_map, value)
            elif isinstance(value, list):  # list of scalars or documents
                if len(value) == 0:  # empty list
                    result[key] = []
                elif isinstance(value[0], dict):  # list of documents
                    result[key] = [mapdoc(query_map, element) for element in value]
                else:  # list of scalars
                    result[key] = [query_map[operator](element) for element in value]
            else:  # scalar
                result[key] = query_map[operator](value)
        else:  # no mapping for this element
            result[key] = value
    return result

def init_storage():
    print('Creating MongoDB connection')
    setting.store_connection = MongoClient() # TODO: make this thread-safe
    print('Setting MongoDB database to', setting.store_dbname)
    setting.store_db = setting.store_connection[setting.store_dbname]

class Item(BareItem):
    """
    Item: class for reading and writing objects from/to a particular form of storage.
    This class adds storage-dependent methods to the base class.
    """
    @classmethod
    def create_collection(cls):
        """
        create_collection(cls)
        Create collection cls.name, unless this is already present.
        """
        coll_list = setting.store_db.collection_names()
        if cls.name not in coll_list:
            setting.store_db.create_collection(cls.name)

    @classmethod
    def create_index(cls, index_keys):
        """
        create_index(cls)
        Create index on index_keys, unless this index is already present.
        index_keys is a list of 2-tuples (name, direction), where direction is 1 or -1
        TODO: text index via coll.ensureIndex({'author': 'text', 'content': 'text'})
        """
        collection = setting.store_db[cls.name]
        collection.ensure_index(index_keys, unique=False)

    @classmethod
    def query(cls, doc):
        """
        query(cls, doc): dict
        Make query from dictionary doc.
        """
        return translate_query(doc)

    @classmethod
    def count(cls, doc):
        """
        count(cls, doc): integer
        Find zero or more documents in collection, and count them.
        doc: dictionary specifying the query, e.g. {'id': '1234'}
        """
        sequence = setting.store_db[cls.name].find(filter=cls.query(doc))
        return sequence.count()

    @classmethod
    def find(cls, doc, skip=0, limit=0, sort=None):
        """
        find(cls, doc): list
        Find zero or more documents in collection, and return these in the
        form of a list of 'cls' instances. Assumption: stored documents are valid.
        doc: dictionary specifying the query, e.g. {'id': '1234'}
        """
        sequence = setting.store_db[cls.name].find(filter=cls.query(doc),
                                                   skip=skip, limit=limit, sort=sort)
        result = [cls(item) for item in sequence]
        return result

    @classmethod
    def lookup(cls, oid):
        """
        lookup(cls, oid): item
        Return first item in collection matching the given primary key (id),
        or None if no item matches this key.
        oid: primary key (string)
        """
        item = setting.store_db[cls.name].find_one({'id':oid})
        return cls(item)

    @classmethod
    def read(cls, doc):
        """
        read(cls, doc): item
        Return first item in collection matching the given query,
        or None if no item matches this query.
        doc: dictionary specifying the query, e.g. {'id': 1234}
        """
        item = setting.store_db[cls.name].find_one(cls.query(doc))
        return cls(item)

    def write(self, validate=True):
        """
        write(self): id
        Save document contained in this instance.
        TODO: use JSend specification in write(), set_field(), append_field(), remove()
        Return value {'status':SUCCESS, 'id':<document id>} or {'status':FAIL, 'id':None}.
        """
        new = getattr(self, 'id', '') == ''
        self['mtime'] = datetime.now()
        if new:
            self['_id'] = ObjectId()
            self['id'] = str(self['_id'])
            self['active'] = True
            self['ctime'] = self['mtime']
        if validate:
            validate_result = self.validate(self)
            if not validate_result['status']:
                message = "document {}\ndoes not validate because of error\n{}\n".\
                    format(self, validate_result['error'])
                return {'status':FAIL, 'message':message}
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
        oid = self['_id']
        collection = setting.store_db[self.name]
        result = collection.update_one({'id':oid}, {'$set':{key:value}})
        return {'status':'successs' if result.modified_count == 1 else FAIL, 'id': self['id']}

    def append_field(self, key, value):
        oid = self['_id']
        collection = setting.store_db[self.name]
        result = collection.update_one({'_id':oid}, {'$addToSet':{key:value}})
        return {'status':SUCCESS if result.modified_count == 1 else FAIL, 'id': self['id']}

    def remove(self):
        """
        remove(self): doc
        Remove item from collection.
        """
        oid = self['_id']
        collection = setting.store_db[self.name]
        result = collection.delete_one({'_id':oid})
        return {'status':SUCCESS if result.deleted_count == 1 else FAIL, 'id': self['id']}
