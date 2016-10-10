# -*- coding: utf-8 -*-
"""
covert.engine.mongodb
-----
Objects and functions related to the MongoDB storage engine.
"""

from datetime import datetime
from pymongo import MongoClient
from ..model import BareItem, mapdoc
from .. import setting
from bson.objectid import ObjectId

def init_storage():
    print('setting MongoDB connection')
    setting.store_connection = MongoClient() # TODO: make this thread-safe
    print('setting MongoDB database to', setting.store_dbname)
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
        qdoc = dict((name, value) for name, value in doc.items()
                     if name in cls.fields and value)
        return qdoc

    # key op value           MongoDB query
    # key == value           {key: value}
    # key =~ value           {key: {'$regex':value}}
    # key [] value1, value2  {key: {'$gte': value1, '$lte': value2}}
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
        Return value {'ok':True, 'id':<document id>} or {'ok':False, 'id':None}.
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
            if not validate_result['ok']:
                message = "document {}\ndoes not validate because of error\n{}\n".\
                    format(self, validate_result['error'])
                return {'ok': False, 'error': message}
        try:
            doc = mapdoc(self.wmap, self)
            collection = setting.store_db[self.name]
            if new:
                result = collection.insert_one(doc)
                return {'ok':True, 'id':str(result.inserted_id)}
            else:
                result = collection.replace_one({'_id':self['_id']}, doc)
                return {'ok':True, 'id':str(result.upserted_id)}
        except Exception as e:
            message = 'document {}\nnot written because of error\n{}\n'.format(doc, str(e))
            return {'ok': False, 'id': None, 'error': message}

    # methods to set references (update database directly)
    def set_field(self, key, value):
        oid = self['_id']
        collection = setting.store_db[self.name]
        result = collection.update_one({'id':oid}, {'$set':{key:value}})
        return {'ok': result.modified_count == 1, 'id': self['id']}

    def append_field(self, key, value):
        oid = self['_id']
        collection = setting.store_db[self.name]
        result = collection.update_one({'_id':oid}, {'$addToSet':{key:value}})
        return {'ok': result.modified_count == 1, 'id': self['id']}

    def remove(self):
        """
        remove(self): doc
        Remove item from collection.
        """
        oid = self['_id']
        collection = setting.store_db[self.name]
        result = collection.delete_one({'_id':oid})
        return {'ok': result.deleted_count == 1, 'id': self['id']}
