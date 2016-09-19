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
        Make query (dictionary) from dictionary doc, using only known fields and
        non-null values.
        """
        qdoc = dict((name, value) for name, value in doc.items()
                     if name in cls.fields and value)
        return qdoc

    @classmethod
    def count(cls, qdoc={}):
        """
        count(cls, qdoc): integer
        Find zero or more documents in collection, and count them.
        qdoc: dictionary specifying the query, e.g. {'id': '1234'}
        """
        cursor = setting.store_db[cls.name].find(filter=cls.query(qdoc))
        return cursor.count()

    @classmethod
    def find(cls, qdoc={}, skip=0, limit=0, sort=None):
        """
        find(cls, qdoc): list
        Find zero or more documents in collection, and return these in the
        form of a list of 'cls' instances. Assumption: stored documents are valid.
        qdoc: dictionary specifying the query, e.g. {'id': '1234'}

        Regular expressions:
            db.collection.find({'family':{'$regex':'^Fel'}}), or
            rx = re.compile(r'^Fel')
            db.collection.find({'family':rx})
        """
        cursor = setting.store_db[cls.name].find(filter=cls.query(qdoc),
                                                 skip=skip, limit=limit, sort=sort)
        result = [cls(doc) for doc in cursor]
        return result

    @classmethod
    def lookup(cls, oid):
        """
        lookup(cls, oid): doc
        Return first document in collection matching the given primary key (id),
        or None if no document matches this key. Assumption: stored documents are valid.
        oid: primary key (string)
        """
        doc = setting.store_db[cls.name].find_one({'id':oid})
        return cls(doc)

    @classmethod
    def read(cls, qdoc):
        """
        read(cls, qdoc): doc
        Return first document in collection matching the given query,
        or None if no document matches this query. Assumption: stored documents are valid.
        qdoc: dictionary specifying the query, e.g. {'id': 1234}
        """
        doc = setting.store_db[cls.name].find_one(cls.query(qdoc))
        return cls(doc)

    def write(self, validate=True):
        """
        write(self): id
        Save document contained in this instance.
        Return value {'ok':True, 'id':<document id>} or {'ok':False, 'id':None}.
        """
        new = not ('id' in self and self['id'])
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
    @classmethod
    def set_field(cls, oid, key, value):
        result = setting.store_db[cls.collection].update_one({'id':oid}, {'$set':{key:value}})
        return {'ok': result.modified_count == 1, 'id': oid}

    @classmethod
    def append_field(cls, oid, key, value):
        result = setting.store_db[cls.collection].update_one({'id':oid}, {'$addToSet':{key:value}})
        return {'ok': result.modified_count == 1, 'id': oid}

    def remove(self):
        """
        remove(self): doc
        Remove document from collection.
        """
        oid = self['_id']
        return setting.store_db[self.name].delete_one({'_id':oid})
        return {'ok': result.deleted_count == 1, 'id': str(oid)}
