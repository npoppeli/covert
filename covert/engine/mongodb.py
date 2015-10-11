# -*- coding: utf-8 -*-
"""
covert.engine.mongodb
-----
Objects and functions related to the MongoDB storage engine.
"""

from datetime import datetime
from pymongo.connection import MongoClient
from ..model import BareItem, mapdoc
from bson.objectid import ObjectId

store_name = ''
store_conn, store_db = None, None

def init_storage():
    global store_name, store_conn, store_db
    store_name = 'local'
    store_conn = MongoClient()
    store_db = store_conn[store_name]

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
        coll_list = store_db.collection_names()
        if cls.name not in coll_list:
            store_db.create_collection(cls.name)

    @classmethod
    def create_index(cls, index_keys):
        """
        create_index(cls)
        Create index on index_keys, unless this index is already present.
        index_keys is a list of 2-tuples (name, direction), where direction is 1 or -1
        TODO: text index via coll.ensureIndex({'author': 'text', 'content': 'text'})
        """
        collection = store_db[cls.name]
        collection.ensure_index(index_keys, unique=False)

    @classmethod
    def query(cls, doc):
        """
        query(cls, doc): dict
        Make query (dictionary) from dictionary doc, using only known fields and
        non-null values.
        """
        qdoc = dict((name, value) for name, value in doc.items()
                     if name in cls.fields() and value)
        return qdoc

    @classmethod
    def count(cls, qdoc={}):
        """
        count(cls, qdoc): integer
        Find zero or more documents in collection, and count them.
        qdoc: dictionary specifying the query, e.g. {'id': '1234'}
        """
        cursor = store_db[cls.name].find(spec=cls.query(qdoc))
        return cursor.count()

    @classmethod
    def find(cls, qdoc={}, skip=0, limit=0, fields=None, sort=None):
        """
        find(cls, qdoc): list
        Find zero or more documents in collection, and return these in the
        form of a list of instances of 'cls'. Assumption: stored documents are valid.
        qdoc: dictionary specifying the query, e.g. {'id': '1234'}

        Regular expressions:
            db.collection.find({'family':{'$regex':'^Fel'}}), or
            rx = re.compile(r'^Fel')
            db.collection.find({'family':rx})
        """
        cursor = store_db[cls.name].find(spec=cls.query(qdoc), skip=skip, limit=limit,
                                           fields=fields, sort=(sort if sort else cls.index))
        result = [ cls(doc) for doc in cursor ]
        return result

    @classmethod
    def lookup(cls, idval):
        """
        lookup(cls, idval): doc
        Return first document in collection matching the given primary key (id),
        or None if no document matches this key. Assumption: stored documents are valid.
        idval: primary key (string)
        """
        doc = store_db[cls.name].find_one({'id':idval})
        return cls(doc)

    @classmethod
    def read(cls, qdoc):
        """
        read(cls, qdoc): doc
        Return first document in collection matching the given query,
        or None if no document matches this query. Assumption: stored documents are valid.
        qdoc: dictionary specifying the query, e.g. {'id': 1234}
        """
        doc = store_db[cls.name].find_one(cls.query(qdoc))
        return cls(doc)

    def write(self, validate=True, debug=False):
        """
        write(self): id
        Save document contained in this instance.
        Return value {'ok':True, 'id':<document id>} or {'ok':False, 'id':None}.
        """
        now = datetime.now()
        self['mtime'] = now
        if ('_id' not in self) or (self['_id'] == ''): # new item
            self['_id'] = ObjectId()
            self['id'] = str(self['_id'])
            self['active'] = True
            self['ctime'] = now
        if validate:
            validate_result = self.validate(self)
            if not validate_result['ok']:
                print("document {}\ndoes not validate because of error\n{}\n".format(self, validate_result['error']))
                return {'ok': False}
        doc = mapdoc(self._wmap, self, debug=debug)
        try:
            result = store_db[self.name].save(doc)
            return {'ok': result != None, 'id': result}
        except Exception as e:
            print("document {}\ndoes not save because of error\n{}\n".format(doc, str(e)))
            return {'ok': False, 'id': None}

    def remove(self):
        """
        remove(self): doc
        Remove document from collection.
        Return value should be {'ok':1.0, 'err':None}.
        """
        return store_db[self.name].remove(self['_id'])
