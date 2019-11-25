# -*- coding: utf-8 -*-
"""Objects and functions related to the RethinkDB storage engine.

This module defines the Item class and an initialization function for the storage engine.
The Item class encapsulates the details of the storage engine.
"""

import ast
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

class Translator(ast.NodeVisitor):
    """Instances of this class translate a filter in the form of a compiled
    Python expression to an instance of the RqlQuery class.

    A filter is a restricted form of Python expression.
    Field names are written as variables. Constants are always strings.
    Allowed boolean operators: and, not.
    Allowed binary operators: ==, ~=, <, <=, >, >=, in, % (match regex).
    Fields with 'multiple' property (list-valued fields) have a special query condition,
    since RethinkDB makes a distinction between search scalar field  and search list field.
    """
    def  __init__(self, cmap, wmap, meta):
        self.cmap = cmap
        self.wmap = wmap
        self.meta = meta

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
    def visit_Dict(self, n):
        return dict(zip(self.visit_keys(n), self.visit_values(n)))
    def visit_BinOp(self, n):
        key, value = self.visit(n.left), self.visit(n.right)
        operator = self.visit(n.op)
        return self.CompareOrBin(key, operator, self.V_(key, value))
    def visit_BoolOp(self, n):
        operator = self.visit(n.op)
        args = self.visit_values(n)
        if operator == '$or':
            result = args[0] | args[1]
            for arg in args[2:]:
                result = result | arg
        else: # operator = '$and'
            result = args[0] & args[1]
            for arg in args[2:]:
                result = result & arg
        return result
    def visit_Compare(self, n):
        key, operator = self.visit(n.left), self.visit(n.ops[0])
        if operator == '$in':
            value1, value2 = self.visit(n.comparators[0])
            return (r.row[key] >= self.V_(key, value1)) & (r.row[key] <= self.V_(key, value2))
        else:
            value1 = self.visit(n.comparators[0])
            return self.CompareOrBin(key, operator, self.V_(key, value1))
    def CompareOrBin(self, key, operator, value):
        if self.meta[key].multiple:
            if   operator == '$eq':    func = lambda r: r.row[key] == value
            elif operator == '$ne':    func = lambda r: r.row[key] != value
            elif operator == '$regex': func = lambda r: r.row[key].match(value)
            elif operator == '$lt':    func = lambda r: r.row[key] <  value
            elif operator == '$le':    func = lambda r: r.row[key] <= value
            elif operator == '$gt':    func = lambda r: r.row[key] >  value
            # else: operator == '$ge'
            else:                      func = lambda r: r.row[key] >= value
            return r.row[key].contains(func)
        else:
            if   operator == '$eq':    return r.row[key] == value
            elif operator == '$ne':    return r.row[key] != value
            elif operator == '$regex': return r.row[key].match(value)
            elif operator == '$lt':    return r.row[key] <  value
            elif operator == '$le':    return r.row[key] <= value
            elif operator == '$gt':    return r.row[key] >  value
            # else: operator == '$ge'
            else:                      return r.row[key] >= value

def init_storage():
    """Initialize storage engine."""
    setting.connection = r.connect(db=setting.dbname).repl()
    dbname = setting.dbname
    setting.item_db = r.db(dbname)
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
        coll_list = r.table_list().run(setting.connection)
        if cls.name not in coll_list:
            r.table_create(cls.name).run(setting.connection)

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
                index_list = table.index_list().run(setting.connection)
                if el[0] not in index_list:
                    table.index_create(el[0]).run(setting.connection)

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
        try:
            root = compile(expr, '', 'eval', ast.PyCF_ONLY_AST)
        except SyntaxError as e:
            logger.debug(c._("Item.filter: expr = {}").format(expr))
            logger.debug(c._("Exception '{}'").format(e))
            raise
        translator = Translator(cls.cmap, cls.wmap, cls.meta)
        try:
            result = translator.visit(root.body)
            return result
        except Exception as e:
            logger.debug(str(e))
            logger.debug(c._("Item.filter: expr = {}").format(expr))
            logger.debug(c._("Item.filter: root = {}").format(ast.dump(root)))
            return None

    @classmethod
    def max(cls, field):
        """Find maximum value in collection of field value.

        Go through all items in collection, and determine maximum value of 'field'.
        Arguments:
            field (str): field name

        Returns:
            any: maximum value.
        """
        result = r.table(cls.name).max(field).run(setting.connection)
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
        rql_query = cls.filter(fltr)
        query = r.table(cls.name).filter(rql_query)
        result = query.count().run(setting.connection)
        logger.debug('Item.count: query gives {} items'.format(result))
        return result

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
        rql_query = cls.filter(fltr)
        query = r.table(cls.name).filter(rql_query)
        if skip:  query = query.skip(skip)
        if limit: query = query.limit(limit)
        if sort:
            sort_spec = [r.asc(el[0]) if el[1] == 1 else r.desc(el[0]) for el in sort]
        else:
            sort_spec = [r.asc('_skey')]
        query = query.order_by(*sort_spec)
        count = query.count().run(setting.connection)
        logger.debug('Item.find: query gives {} items'.format(count))
        cursor = query.run(setting.connection)
        return [cls(item) for item in cursor]

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
        rql_query = cls.filter(fltr)
        query = r.table(cls.name).filter(rql_query)
        if query is None:
            logger.debug('project: query is None')
        if sort:
            sort_spec = [r.asc(el[0]) if el[1] == 1 else r.desc(el[0]) for el in sort]
        else:
            sort_spec = [r.asc('_skey')]
        if mono:
            query = query.pluck(field)
        else:
            query = query.pluck(*field)
        query = query.order_by(*sort_spec)
        cursor = query.run(setting.connection)
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
        item = r.table(cls.name).get(oid).run(setting.connection)
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
        rql_query = cls.filter(doc)
        query = r.table(cls.name).filter(rql_query)
        result = list(query.run(setting.connection))
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
                result = collection.insert(doc).run(setting.connection)
                reply= {'status':SUCCESS, 'data':self['id'], 'message':str(result.inserted)}
            else:
                result = collection.get(self['_id']).replace(doc).run(setting.connection)
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
            result = collection.get(item_id).update({key:doc[key]}).run(setting.connection)
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
            result = collection.get(item_id).update({key:r.row[key].append(doc[key])}).run(setting.connection)
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
        result = collection.get(item_id).delete().run(setting.connection)
        reply = {'status':SUCCESS if result.deleted == 1 else FAIL, 'data': item_id}
        report_db_action(reply)
        return reply
