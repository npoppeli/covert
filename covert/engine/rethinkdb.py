# -*- coding: utf-8 -*-
"""
covert.engine.rethinkdb
-----
Objects and functions related to the RethinkDB storage engine.
"""

import rethinkdb as r
from ..model import BareItem

store_name = ''
store_conn, store_db = None, None

def init_storage():
    global store_name, store_conn, store_db
    store_name = 'develop'
    store_conn = r.connect(db=store_name)
    store_db = store_conn.db(store_name)

class Item(BareItem):
    """
    Item: class for reading and writing objects from/to a particular form of storage.
    This class adds methods to the data attributes of the base class.
    """
    def __init__(self, doc={}):
        """
        __init__(self, doc)
        Initialize instance from dictionary doc.
        """
        for (key, value) in doc.items():
            self[key] = value

    @classmethod
    def create_table(cls):
        """
        create_table(cls)
        Create table (collection) cls._name, unless this is already present.
        A useful feature of MongoDB is automatic creation of databases and
        collections, so this is not strictly necessary.
        """
        table_list = store_db.tableList().run(store_conn)
        if cls._name not in table_list:
            store_db.tableCreate(cls._name).run(store_conn)

    @classmethod
    def create_index(cls, key):
        """
        create_index(cls)
        Create index on cls._key, unless this index is already present.
        This is a no-op if the key == 'id', since in RethinkDB this is
        the primary key, which is indexed by default.
        """
        if cls._key != 'id':
            table = store_db.table(cls._name)
            index_list = table.indexList().run(store_conn)
            if cls._key not in index_list:
                table.indexCreate(cls._key).run(store_conn)

    @classmethod
    def convert(cls, doc):
        """
        convert(cls, doc): item
        Convert string representation of item to item with typed fields.
        """
        result = {}
        for name, value in doc.items():
            convert = cls._skeleton[name].convert:
            if cls._skeleton[name].multiple:
                result[name] = [ convert(e) for e in value ]
            else:
                result[name] = convert(value)
        return cls(result)

    def display(self):
        """
        display(self): pnode
        Create pnode (rendering structure).
        {'@family': 'item', '@genus': '',
         content: [
            {'@family': 'field', '@genus': '', 'label': LABEL, 'children': [...] },
            {'@family': 'field', '@genus': '', 'label': LABEL, 'children': [...] },
            ...
          ]
        }
        """
        result = []
        for name, field in self._skeleton.items():
            field_value = self[name]
            if field.multiple:
                childlist =  [ node('show', field.schema, value=e) for e in field_value  ]
            else:
                childlist = [ node('show', field.schema, value=field_value) ]
            result.append(node('field', '',
                               label=field.label, children=childlist,
                               hidden=field.hidden, multiple=field.multiple))
        return node('item', '', label=self._name, content=result)

    @classmethod
    def query(cls, doc):
        """
        query(cls, doc): dict
        Make query (dictionary) from dictionary doc, using only known fields and
        non-null values.
        """
        qdoc = dict((name, value) for name, value in doc.items()
                     if name in cls._fields and value)
        return qdoc

    @classmethod
    def find(cls, qdoc={}, skip=0, limit=0, fields=None, sort=None):
        """
        find(cls, qdoc): list
        Find zero or more documents in collection, and return these in the
        form of a list of instances of 'cls'.
        qdoc: dictionary specifying the query, e.g. {'id': '1234'}

        Regular expressions:
            db.collection.find({'family':{'$regex':'^Fel'}}), or
            rx = re.compile(r'^Fel')
            db.collection.find({'family':rx})

        r.table('table').filter(lambda item: item['author'].match('^A'))
        """
        table = store_db.table(cls._name)
        cursor = table.indexList().run(store_conn)
        result = [cls(cls._validate(doc)) for doc in
                  cls._collection.find(spec=cls.query(qdoc), skip=skip, limit=limit,
                                       fields=fields, sort=sort)]
        return result

    @classmethod
    def get(cls, key):
        """
        lookup(cls, key): doc
        Return first document in collection matching the given key,
        or None if no document matches this key.
        key: primary or secondary key (string)
        """
        result = cls._collection.find_one({cls._key:key})
        if result:
            return cls(cls._validate(result))
        else:
            return None

    @classmethod
    def read(cls, qdoc):
        """
        read(cls, qdoc): doc
        Return first document in collection matching the given query,
        or None if no document matches this query.
        qdoc: dictionary specifying the query, e.g. {'id': 1234}
        """
        result = cls._collection.find_one(cls.query(qdoc))
        if result:
            return cls(cls._validate(result))
        else:
            return None

    def remove(self):
        """
        remove(self): doc
        Remove document from collection.
        Returns document:
        { 'unchanged':0, 'skipped':0, 'replaced':1,
          'inserted':0,
          'errors':0, 'deleted':1 }
        TODO return engine-independent return value
        """
        return self._collection.remove()

    def write(self):
        """
        write(self): doc
        Write (or update) document contained in this instance.
        Returns document:
        { 'unchanged':0, 'skipped':0, 'replaced':0,
          'inserted':1, 'generated_keys':['key'],
          'errors':0, 'deleted':0 }
        { 'unchanged':0, 'skipped':0, 'replaced':1,
          'inserted':1,
          'errors':0, 'deleted':0 }
        TODO engine-independent return value
        """
        doc = self._validate(self)
        return self._collection.save(doc)
