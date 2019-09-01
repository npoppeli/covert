# -*- coding: utf-8 -*-
"""Objects and functions related to the RethinkDB storage engine.

This module defines the Item class and an initialization function for the storage engine.
The Item class encapsulates the details of the storage engine.
"""

from datetime import datetime
import rethinkdb as r
from ..common import SUCCESS, ERROR, FAIL, logger, InternalError
from ..model import BareItem, mapdoc, Visitor
from .. import setting
from .. import common as c
from ..event import event
from bson.objectid import ObjectId

def report_db_action(result):
    message = "{}: status={} data={} ".format(datetime.now(), result['status'], result['data'])
    if 'message' in result:
        message += result['message']
    if setting.debug > 1:
        logger.debug(message)

class Translator(Visitor):
    """Translate query to form suitable for this storage engine.

    A filter is a sequence of terms or nested clauses (and, or). A term is a tuple (op, value) or
    (op, value1, value2), where 'op' is a 2-character string specifying a filter operator.
    Fields with 'multiple' property (list-valued fields) have a normal query condition.
    RethinkDB makes a distinction between search scalar field  and search list field, so
    this needs rewriting.

    TODO: add possibility to search through array fields
    """
    def  __init__(self, wmap, name):
        self.wmap = wmap
        self.chain = r.table(name)

    def visit_filter(self, node):
        for term in node.terms:
            new_term = self.visit(term)
            for field, cond in new_term.items():
                operator = cond[0]
                if operator   in ('==', 'eq'):
                    self.chain = self.chain.filter(r.row[field] == cond[1])
                elif operator in ('<>', '!='):
                    self.chain = self.chain.filter(r.row[field] != cond[1])
                elif operator in ('=~', 're'):
                    self.chain = self.chain.filter(r.row[field].match(cond[1]))
                elif operator in ('[]', 'in'):
                    self.chain = self.chain.filter((r.row[field] >= cond[1]) & (r.row[field] <= cond[2]))
                elif operator in ('<', 'lt'):
                    self.chain = self.chain.filter(r.row[field] < cond[1])
                elif operator in ('<=', 'le'):
                    self.chain = self.chain.filter(r.row[field] <= cond[1])
                elif operator in ('>', 'gt'):
                    self.chain = self.chain.filter(r.row[field] > cond[1])
                elif operator in ('>=', 'ge'):
                    self.chain = self.chain.filter(r.row[field] >= cond[1])
        return self.chain

    def visit_and(self, node):
        logger.debug('Translator: visit_and not implemented yet')
        return {}

    def visit_or(self, node):
        logger.debug('Translator: visit_or not implemented yet')
        return {}

    def visit_term(self, node):
        field = node.field
        operator = node.operator
        wmap = self.wmap
        value1 = wmap[field](node.value1) if (node.value1 and field in wmap) else node.value1
        value2 = wmap[field](node.value2) if (node.value2 and field in wmap) else node.value2
        return {field: (operator, value1, value2)}


def init_storage():
    """Initialize storage engine."""
    setting.store_connection = r.connect(db=setting.store_dbname).repl()
    dbname = setting.store_dbname
    setting.store_db = r.db(dbname)
    if setting.debug >= 2:
        logger.debug(c._("Create RethinkDB connection, set database to '{}'").format(dbname))

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
        coll_list = r.table_list().run(setting.store_connection)
        if cls.name not in coll_list:
            r.table_create(cls.name).run(setting.store_connection)

    @classmethod
    def create_index(cls, index_keys):
        """Create index on index_keys.

        Create index on index_keys, unless this index is already present.

        Arguments:
            index_keys (list): list of 2-tuples (name, direction), where direction is 1 or -1

        Returns:
            None
        """
        for el in index_keys:
            if el[0] != 'id':
                table = r.table(cls.name)
                index_list = table.index_list().run(setting.store_connection)
                if el[0] not in index_list:
                    table.index_create(el[0]).run(setting.store_connection)

    @classmethod
    def filter(cls, expr):
        """Create filter from filter expression `expr`.

        In the view methods, filters are specified as Python expressions.
        Fields with 'multiple' property (list-valued fields) have a normal query condition.
        Since RethinkDB differentiates search scalar field and search list field, we must use
        information from the model to rewrite the query.

        Arguments:
            expr (str): Python expression.

        Returns:
            selection: RethinkDB sequence
        """
        if not expr:
            return None
        translator = Translator(cls.wmap, cls.name)
        return translator.visit(expr)

    @classmethod
    def max(cls, field):
        """Find maximum value in collection of field value.

        Go through all items in collection, and determine maximum value of 'field'.
        Arguments:
            field (str): field name

        Returns:
            any: maximum value.
        """
        result = r.table(cls.name).max(field).run(setting.store_connection)
        return result[field]

    @classmethod
    def count(cls, fltr):
        """Count items in collection that match a given query.

        Find zero or more items (documents) in collection, and count them.

        Arguments:
            fltr (str): Python expression.

        Returns:
            int: number of matching items.
        """
        cursor = cls.filter(fltr)
        return cursor.count().run(setting.store_connection)

    @classmethod
    def find(cls, fltr=None, skip=0, limit=0, sort=None):
        """Retrieve items from collection.

        Find zero or more items in collection, and return these in the
        form of a list of 'cls' instances. Assumption: stored items are valid.

        Arguments:
            fltr  (str) : Python expressions.
            skip  (int) : number of items to skip.
            limit (int) : maximum number of items to retrieve.
            sort  (list): sort specification.

        Returns:
            list: list of 'cls' instances.
        """
        cursor = cls.filter(fltr)
        if skip:  cursor = cursor.skip(skip)
        if limit: cursor = cursor.limit(limit)
        if sort:
            sort_spec = [r.asc(el[0]) if el[1] == 1 else r.desc(el[0]) for el in sort]
        else:
            sort_spec = [r.asc('_skey')]
        cursor = cursor.order_by(*sort_spec)
        result = cursor.run(setting.store_connection)
        return [cls(item) for item in result]

    @classmethod
    def project(cls, field, fltr, sort=None, bare=False):
        """Retrieve items from collection, and return selection of fields.

        Find zero or more items in collection, and return these in the
        form of a list of tuples. Assumption: stored items are valid.

        Arguments:
            fltr  (str)         : Python expression.
            field (string, list): name(s) of field(s) to include.
            sort  (list)        : sort specification.
            bare  (bool)        : if True, return only bare values.

        Returns:
            list: list of field values, tuples or dictionaries
        """
        mono = isinstance(field, str)
        cursor = cls.filter(fltr)
        if sort:
            sort_spec = [r.asc(el[0]) if el[1] == 1 else r.desc(el[0]) for el in sort]
        else:
            sort_spec = [r.asc('_skey')]
        if mono:
            cursor = cursor.pluck(field)
        else:
            cursor = cursor.pluck(*field)
        cursor = cursor.order_by(*sort_spec)
        result = cursor.run(setting.store_connection)
        if bare:
            if mono:
                return [doc[field] for doc in result]
            else:
                return [tuple(doc[f] for f in field) for doc in result]
        else:
            return list(result)

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
        item = r.table(cls.name).get(oid).run(setting.store_connection)
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
        result = list(r.table(cls.name).filter(cls.filter(doc)).run(setting.store_connection))
        if len(result) == 0:
            return None
        else:
            return cls(result[0])

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
            self['id'] = str(ObjectId())
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
        doc = {key:value for key, value in mapdoc(self.wmap, self).items()
                         if not key.startswith('__')}
        collection = r.table(self.name)
        if setting.nostore: # do not write anything to the database
            reply = {'status':SUCCESS, 'data':'simulate '+('insert' if new else 'update')}
            report_db_action(reply)
            return reply
        try:
            if new:
                result = collection.insert(doc).run(setting.store_connection)
                reply= {'status':SUCCESS, 'data':self['id'], 'message':str(result.inserted)}
            else:
                result = collection.get(self['_id']).replace(doc).run(setting.store_connection)
                reply = {'status':SUCCESS, 'data':self['id'], 'message':str(result.replaced)}
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
        item_id = self['id']
        collection = r.table(self.name)
        if setting.nostore: # don't write to the database
            reply = {'status': SUCCESS, 'data': 'simulate update'}
            report_db_action(reply)
            return reply
        doc = mapdoc(self.wmap, {key:value})
        try:
            result = collection.get(item_id).update({key:doc[key]}).run(setting.store_connection)
            reply = {'status':SUCCESS if result.changes == 1 else FAIL,
                     'data': item_id, 'message':str(result.replaced)}
            report_db_action(reply)
            if reply['status'] == FAIL:
                message = c._('{} {}\nnot updated, replaced={}').format(self.name, self, result.replaced)
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
        item_id = self['id']
        collection = r.table(self.name)
        if setting.nostore: # don't write to the database
            reply = {'status': SUCCESS, 'data': 'simulate update'}
            report_db_action(reply)
            return reply
        doc = mapdoc(self.wmap, {key:value})
        try:
            result = collection.get(item_id).update({key:r.row[key].append(doc[key])}).run(setting.store_connection)
            reply = {'status':SUCCESS if result.changes == 1 else FAIL,
                     'data': item_id, 'message':str(result.replaced)}
            report_db_action(reply)
            if reply['status'] == FAIL:
                message = c._('{} {}\nnot updated, replaced={}').format(self.name, self, result.replaced)
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
        item_id = self['id']
        collection = r.table(self.name)
        result = collection.get(item_id).delete().run(setting.store_connection)
        reply = {'status':SUCCESS if result.deleted == 1 else FAIL, 'data': item_id}
        report_db_action(reply)
        return reply
