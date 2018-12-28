# -*- coding: utf-8 -*-
"""Objects and functions related to models.

A model defines the structure of an item. A basic item is a flat dictionary (all values are
scalars). A more complicated item has lists and dictionaries as values. This is fully recursive.

Instead of embedding a basic item of class B inside an item of class A, you can also add
references to items of class B inside an item of class A ('linking').

A reference to an item is essentially a 3-tuple (collection name, item id, description).
The third item is dynamically computed upon using the item reference.

Transformations are an important part of working with items. Each model has mapping functions for
reading from/writing to storage, and for converting from/displaying as HTML (see diagram below).

storage   -> [JSON document] -> read    -> [item] -> display -> [item']         -> HTML page
HTML form -> [item']         -> convert -> [item] -> write   -> [JSON document] -> storage

Other important transformations are the structure transformations of flattening and unflattening.
In most cases these transformations do not require knowledge of the model definition, but there
are two exceptions (described in the code below).
"""

from bisect import bisect_left, bisect_right
from copy import deepcopy
from collections import OrderedDict
from voluptuous import Schema, Optional, MultipleInvalid
from .atom import atom_map, EMPTY_DATETIME
from .common import InternalError, SUCCESS, FAIL, logger
from .controller import exception_report
from . import setting

# functions for flattening and unflattening items (documents)
def _flatten(doc, prefix, keys):
    """Generator for flattening an item (document).

    The result of flattening an item is a flat dictionary. The keys of this flat dictionary are
    the paths in the original item, e.g. 'children', 'children.0', 'children.0.firstname'.
    This generator is used by Item.flatten().

    Arguments:
        doc (Item): original document.
        prefix (str): path prefix (for recursion).
        keys: keys of doc, in model definition order.

    Yields:
        (key, value): key-value pair to build up flat dictionary.
    """
    for key in [el for el in keys if el in doc.keys()]: # keys in model order
        value = doc[key]
        sub_prefix = '{}{}.'.format(prefix, key)
        if isinstance(value, dict):  # embedded document
            yield from _flatten(value, sub_prefix, keys)
        elif isinstance(value, list):  # list of scalars or documents
            if len(value) == 0:  # empty list
                # inspect schema to determine whether we should add an empty scalar ''
                # or an empty dict: {key1: '', key2: '', ...}
                schema = doc.schema[key][0]
                if isinstance(schema, dict):
                    for subkey in schema.keys():
                        yield '{}0.{}'.format(sub_prefix, subkey), ''
                else:
                    yield sub_prefix + '0', ''
            elif isinstance(value[0], dict):  # list of documents
                for sub_key, element in enumerate(value):
                    yield from _flatten(element, sub_prefix+str(sub_key)+'.', keys)
            else:  # list of scalars
                for sub_key, element in enumerate(value):
                    yield sub_prefix + str(sub_key), element
        else:  # scalar
            yield prefix + key, value
    for key in [el for el in doc.keys() if el not in keys]: # keys not defined in model
        yield key, doc[key]

def unflatten(doc, model):
    """Unflatten item (document).

    Unflatten item to (re)create hierarchical structure. A flattened document has keys 'a',
    'a.b', 'a.b.c' etcetera. As preparation, the keys are transformed into lists (this speeds up
    the unflattening), and the document is transformed to a list of 2-tuples, sorted on key.

    Arguments:
        doc   (dict):  flattened document.
        model (class): model class of document

    Returns:
        dict: unflattened item
    """
    list_rep = [(key.split('.'), doc[key]) for key in sorted(doc.keys())]
    # logger.debug('\n'.join(["'{}': '{}'".format(elt[0], str(elt[1])) for elt in list_rep]))
    return _unflatten(list_rep, model.meta)

def _unflatten(list_rep, meta):
    """Function for unflattening an item (document).

    This function is called by unflatten() to do the actual unflattening.

    Arguments:
        list_rep (list): list of (key, value) pairs, sorted on key, where each key is
        a list derived from path (e.g. 'a', 'a.b' or 'a.b.0.c') by splitting on the '.'.

    Returns:
        list|dict: complete dict, or component thereof (dict, list).
    """
    result = {}
    car_list = [elt[0].pop(0) for elt in list_rep]  # take first element (car) from each key
    car_set = set(car_list) # set of (unique) car's is the set of keys of result
    for key in car_set:
        optional = meta[key].optional if key in meta else False
        begin = bisect_left(car_list, key)
        end = bisect_right(car_list, key)
        children = list_rep[begin:end]
        if len(children) == 1: # recursion terminates here
            child = children[0]
            path = child[0]
            if not path: # scalar
                result[key] = child[1]
            elif path[0].isnumeric(): # one-item list
                # RHS = [] if key refers to an optional field, and child[1] is empty
                if optional and not(child[1]):
                    logger.debug("unflatten: '{}' is optional && value empty '{}'".format(key, child[1]))
                    result[key] = []
                else:
                    logger.debug("unflatten: not an edge case, key='{}' value='{}'".format(key, child[1]))
                    result[key] = [child[1]]
            else: # one-item dict
                result[key] = {path[0]:child[1]}
        else: # recursion => value can be nested dict, list of nested dict's or list of scalars
            value = _unflatten(children, meta)
            if isinstance(value, list) and len(value) == 1 and optional and \
                not any(map(bool, value[0].values())):
                logger.debug("unflatten: '{}' is optional && value empty dict '{}'".format(key, str(value)))
                result[key] = []
            else:
                logger.debug("unflatten: not an edge case, key='{}' value='{}'".format(key, str(value)))
                result[key] = value
    # convert a dict with numeric keys to a list
    if car_set and all([key.isnumeric() for key in car_set]):
        return [t[1] for t in sorted(result.items(), key=lambda t: int(t[0]))]
    else:
        return result

def mapdoc(fnmap, doc):
    """Map item (document) by applying functions in function map.

    Map item (dictionary) by applying the functions in the function map 'fnmap'.
    The keys of this map are the field names for a particular model.

    Arguments:
        fnmap (dict): dictionary of mapping functions.
        doc (dict):   item to be mapped (transformed).

    Returns/Yields:
        dict: transformed item (document).
    """
    result = {}
    for key, value in doc.items():
        if key in fnmap: # apply mapping function
            if isinstance(value, dict): # embedded document
                result[key] = mapdoc(fnmap, value)
            elif isinstance(value, list): # list of scalars or documents
                if len(value) == 0: # empty list
                    result[key] = []
                elif isinstance(value[0], dict): # list of documents
                    result[key] = [mapdoc(fnmap, element) for element in value]
                else: # list of scalars
                    result[key] = [fnmap[key](element) for element in value]
            else: # scalar
                result[key] = fnmap[key](value)
        else: # no mapping for this element
            result[key] = value
    return result


class Field:
    """Meta-data for one field in an item.

    The meta-data of a field (component of an item) are derived from the atom and model definitions.

    Attributes:
        * see constructor method
    """
    __slots__ = ('label', 'schema', 'formtype', 'control', 'optional', 'multiple',
                 'auto', 'atomic',  'control', 'enum')
    def __init__(self, label, schema, formtype, optional=False, multiple=False,
                 control='input', auto=False, atomic=True, enum=None):
        """Initialize object.

        Arguments:
            label    (str):   human-readable description of field
            schema   (class): class of atom, used for item validation
            formtype (str):   HTML form type
            control  (str):   HTML input type
            enum     (list):  range of allowed values for enumerated type
            optional (bool):  True if field is optional
            multiple (bool):  True if field is multiple (list)
            auto     (bool):  True if field is auto(matic)
            atomic   (bool):  True if field is atomic
        """
        self.label    = label
        self.schema   = schema
        self.formtype = formtype
        self.control  = control
        self.optional = optional
        self.multiple = multiple
        self.auto     = auto
        self.atomic   = atomic
        self.enum     = enum


class BareItem(dict):
    """Base class for Item.

    The BareItem class defines common data attributes and storage-independent methods.
    The common data attributes are:
        * id     (string):   unique id attribute (unique at least within the collection)
        * _skey  (string):   sort key
        * active (boolean):  True if active item, False if inactive (deleted) item
        * ctime  (datetime): creation time (automatic)
        * mtime  (datetime): modification time (automatic)
    """
    # basics
    ba = atom_map['boolean']
    sa = atom_map['string']
    da = atom_map['datetime']
    name = 'BareItem'
    fields = ['id', '_skey', 'ctime', 'mtime', 'active']
    index = [('id', 1), ('_skey', 1)]
    # validation
    schema    = {'id':sa.schema, '_skey': sa.schema, 'active': ba.schema,
                 'ctime':da.schema, 'mtime':da.schema}
    _validate = None
    _empty    = {'id':'', '_skey': '', 'active':True,
                 'ctime':EMPTY_DATETIME, 'mtime':EMPTY_DATETIME}
    # transformation
    cmap = {'ctime':da.convert, 'mtime':da.convert, 'active': ba.convert}
    dmap = {'ctime':da.display, 'mtime':da.display, 'active': ba.display}
    qmap = {'ctime':da.query,   'mtime':da.query,   'active': ba.query  }
    rmap = {}
    wmap = {}
    # metadata
    meta = OrderedDict()
    meta['id']     = Field(label='Id',       schema='string',   formtype='hidden',  auto=True)
    meta['_skey']  = Field(label='Sort by',  schema='string',   formtype='hidden',  auto=True)
    meta['active'] = Field(label='Actief',   schema='boolean',  formtype='boolean', auto=False,
                           enum=ba.enum, control=ba.control)
    meta['ctime']  = Field(label='Created',  schema='datetime', formtype='hidden',  auto=True)
    meta['mtime']  = Field(label='Modified', schema='datetime', formtype='hidden',  auto=True)

    def __init__(self, doc=None):
        """Initialize item.

        Initialize item in steps:
        1. super-class initialization
        2. update with contents of'empty item'
        3. update with contents of 'doc' (if available):

        Arguments:
            * doc (dict): item read from storage.
        """
        super().__init__()
        empty = deepcopy(self._empty)
        self.update(empty) # necessary in case of bulk import
        if doc:
            try:
                self.update(mapdoc(self.rmap, doc))
            except Exception as e:
                logger.error('Error in applying rmap to doc=%s\n%s',
                             doc, exception_report(e, ashtml=False))

    _format = 'Item {id}'
    def __str__(self):
        """Informal string representation of item.

        Returns:
            str: human-readable representation.
        """
        return self._format.format(**self)

    def __repr__(self):
        """Formal string representation of item.

        Returns:
            str: representation for Python interpreter.
        """
        content = ', '.join(["'{}':'{}'".format(key, self.get(key, '')) for key in self.fields])
        return '{}({})'.format(self.__class__.__name__, content)

    def accept(self, visitor):
        visitor.visit(self)

    @classmethod
    def validate(cls, doc):
        """Validate item.

        Validate document using class-specific validation function.

        Arguments:
            * doc (dict): item to be validated.

        Returns:
            * {'status': 'success', 'data':{} }                   if validation OK
            * {'status': 'fail',    'data':{field1:error1, ...} } if validation not OK
        """
        validator = cls._validate
        try:
            _ = validator(doc)
            return {'status': SUCCESS, 'data':''}
        except MultipleInvalid as e:
            error = '; '.join([str(el) for el in e.errors ])
            return {'status': FAIL, 'data':error}

    @classmethod
    def lookup(cls, oid):
        """Retrieve item with id=oid from storage.

        This is a trivial implementation, overridden by sub-classes.

        Arguments:
            * oid (str): item id.
        """
        item = {'id':oid}
        return cls(item)

    @classmethod
    def convert(cls, doc):
        """Convert item from string form to actual, typed form.

        Convert item with only string values to item with typed values.
        The item can be partially complete.

        Arguments:
            * doc (dict): item read from HTML form.

        Returns:
            dict: item with values according to the model definition
        """
        return mapdoc(cls.cmap, doc)

    def display(self):
        """Convert item to string form.

        Convert item with typed values to item with only string values.

        Returns:
            dict: item with only string fields.
        """
        cls = self.__class__
        item = cls()
        item.update(mapdoc(self.dmap, self))
        return item

    def flatten(self):
        """Flatten item (document).

        Flatten item (document with hierarchical structure) to flat dictionary.

        Returns:
            dict: flattened item.
        """
        flat_dict = OrderedDict()
        for key, value in _flatten(self, '', self.fields):
            flat_dict[key] = value
        return flat_dict

    def copy(self):
        """Make deep copy of item.

        Make deep copy of item, erasing the 'auto' fields, so that it looks new.

        Returns:
            dict: copy of item with 'auto' fields set to 'None'.
        """
        cls = self.__class__
        item = cls()
        clone = deepcopy(self)
        for name in cls.fields:
            if cls.meta[name].auto:
                clone[name] = None
        item.update(clone)
        return item


# Auxiliary classes: Visitor, Filter and friends
class Visitor:
    """Visitor design pattern uses:
    1. instances of Visitor class (or sub-class thereof)
    2. dynamic method determination.
    """
    def visit(self, obj, **kwarg):
        name = 'visit_' + obj.__class__.__name__.lower()
        method = getattr(self, name, None)
        if method:
            return method(obj, **kwarg)
        else:
            return None

class Clause:
    def __init__(self, *terms):
        self.terms = []
        if terms:
            self.terms.extend(terms)

    def add(self, term):
        self.terms.append(term)

    def __contains__(self, key):
        return any([t.field == key for t in self.terms if isinstance(t, Term)])

    def __delitem__(self, key):
        if key in self:
            position = -1
            for n, term in enumerate(self.terms):
                if isinstance(term, Term) and term.field == key:
                    position = n
                    break
            if position >= 0:
                del self.terms[position]

    def __repr__(self):
        return "{}({})".\
            format(self.__class__.__name__, ', '.join([repr(t) for t in self.terms]))

class Filter(Clause):
    pass

class And(Clause):
    pass

class Or(Clause):
    pass

class Term:
    def __init__(self, field, operator, value1, value2=None):
        self.field = field
        self.operator = operator
        self.value1 = value1
        self.value2 = value2

    def __repr__(self):
        if self.value2:
            return "{}({}, {}, {}, {})".\
                   format('Term', repr(self.field), repr(self.operator), repr(self.value1), repr(self.value2))
        else:
            return "{}({}, {}, {})".\
                   format('Term', repr(self.field), repr(self.operator), repr(self.value1))


# Item references
def get_objectid(ref):
    """Retrieve objectid from item reference.

    This function is used as the write map for an item reference.

    Arguments:
        ref (itemref): item reference.

    Returns:
        str: item reference.
    """
    return ref.refid

def display_reference(ref):
    """Generate display form of item reference.

    This function is used as the display map for an item reference.

    Arguments:
        ref (itemref): item reference.

    Returns:
        (str, str, str, str): prefix, infix, URL, postfix.
    """
    if ref.refid is None:
        return '', '', '#', ''
    else:
        return ref.display()


class ItemRef:
    """Reference to Item"""
    collection = 'Item'

    def __init__(self, refid=None):
        """Initialize item reference.

        Arguments:
            refid (str): id of item (default: None, for an empty reference).
        """
        self.refid = refid
        self.str = ''

    def __eq__(self, other):
        """Determine equality of item references.

        Returns:
            bool: self == other.
        """
        return self.__class__.__name__ == other.__class__.__name__ and self.refid == other.refid

    def __ne__(self, other):
        """Determine inequality of item references.

        Returns:
            bool: self != other.
        """
        return self.__class__.__name__ != other.__class__.__name__ or self.refid != other.refid

    def __hash__(self):
        """Calculate hash value.

        Returns:
            int: hash value of self.refid.
        """
        return self.refid.__hash__()

    def __bool__(self):
        """Determine truth value of item reference.

        Returns:
            bool: self.id is not-empty (True)
        """
        return bool(self.refid)

    def __str__(self):
        """Informal string representation of item reference.

        Returns:
            str: human-readable representation.
        """
        return "{}.{}".format(self.collection[0], self.refid[18:] if self.refid else 'null')

    def __repr__(self):
        """Formal string representation of item reference.

        Returns:
            str: representation for Python interpreter.
        """
        return "{}({},{})".format(self.__class__.__name__, self.collection, self.refid)

    def display(self):
        """Display form of item reference.

        Returns:
            str: string to be inserted into render tree.
        """
        model = setting.models[self.collection]
        item = model.lookup(self.refid)
        return '', str(item), '/{}/{}'.format(self.collection.lower(), self.refid), ''

    def lookup(self):
        """Retrieve item referenced by itemref object from storage.

        Returns:
            Item: item retrieved from storage.
        """
        model = setting.models[self.collection]
        return model.lookup(self.refid)

    def lookup_field(self, field):
        """Retrieve one field from item referenced by itemref object from storage.

        Returns:
            Any: field in item retrieved from storage, None if not available.
        """
        model = setting.models[self.collection]
        item = model.lookup(self.refid)
        if item and field in item:
            return item[field]
        else:
            return None


class ParsedModel:
    """Result of parsing a model definition.

    Attributes:
        names  (list):        field names
        index  (list):        indexed fields
        fmt    (str):         format string for string representation
        meta   (OrderedDict): meta-data
        empty  (dict):        empty item
        schema (dict):        schema for validation
        rmap   (dict):        read map
        wmap   (dict):        write map
        dmap   (dict):        display map
        cmap   (dict):        convert map
        qmap   (dict):        query map (variation on 'cmap')
    """

    def __init__(self):
        """Construct parsed model definition."""
        self.names, self.index = [], []
        self.fmt = ''
        self.meta = OrderedDict()
        self.empty = {}
        self.schema = {}
        self.rmap, self.wmap, self.dmap, self.cmap, self.qmap = {}, {}, {}, {}, {}

def parse_model_def(model_def, model_defs):
    """Parse definition of one model.

    Arguments:
        model_def (dict):  model definition to be parsed
        model_defs (list): list of all model definitions
                           (needed for forward references to inner classes)
    """
    pm = ParsedModel() # parsed model definition
    label_index = setting.languages.index(setting.language)
    for line in model_def:
        field_def = line.split()
        if len(field_def) not in (3, 4):
            raise InternalError("field definition '{0}' should have 3 or 4 components".format(line))
        optional_field, multiple_field, auto_field = False, False, False
        if len(field_def) == 3:
            field_name, field_type, field_label = field_def
        else: # n == 4
            field_name, field_type, field_card, field_label = field_def
            auto_field     = field_card == '%'
            multiple_field = field_card in '+*'
            optional_field = field_card in '?*'
            # indexed field: < >
            if field_card in '<>':
                direction = -1 if field_card == '<' else 1
                pm.index.append( (field_name, direction) )
        if field_name == '_format':
            pm.fmt = field_label.replace('_', ' ')
            continue
        schema_key = Optional(field_name) if optional_field else field_name
        pm.names.append(field_name)
        field_label = field_label.replace('_', ' ')
        parts = field_label.split('|')
        field_label = parts[label_index]
        if field_type[0] == '_': # embedded model (comparable to inner class)
            embedded = parse_model_def(model_defs[field_type], model_defs)
            if multiple_field:
                pm.empty[field_name] = [] if optional_field else [embedded.empty]
            elif not optional_field:
                pm.empty[field_name] = embedded.empty
            pm.schema[schema_key] = [embedded.schema] if multiple_field else embedded.schema
            pm.meta[field_name] = Field(label=field_label, schema='dict',
                                        formtype='hidden', control='input',
                                        auto=False, atomic=False,
                                        optional=optional_field, multiple=multiple_field)
            pm.names.extend(embedded.names)
            pm.cmap[field_name] = dict
            pm.dmap[field_name] = dict
            pm.rmap[field_name] = dict
            pm.wmap[field_name] = dict
            pm.qmap[field_name] = None
            pm.cmap.update(embedded.cmap)
            pm.dmap.update(embedded.dmap)
            pm.rmap.update(embedded.rmap)
            pm.wmap.update(embedded.wmap)
            pm.qmap.update(embedded.qmap)
            for name in embedded.names: # necessary for preserving order
                pm.meta[name] = embedded.meta[name]
        elif field_type[0] == '^': # reference to model
            ref_name = field_type[1:]+'Ref'
            ref_class = setting.models[ref_name]
            if ref_name not in setting.models:
                raise InternalError("reference to unknown model '{0}' in {1}".format(ref_name, line))
            # don not extend pm.cmap, since model reference needs no conversion
            pm.dmap[field_name] = display_reference
            pm.rmap[field_name] = ref_class
            pm.wmap[field_name] = get_objectid
            pm.qmap[field_name] = None
            empty_ref = ref_class(None)
            if multiple_field:
                pm.empty[field_name] = [] if optional_field else [empty_ref]
            elif not optional_field:
                pm.empty[field_name] = empty_ref
            pm.schema[schema_key] = [ref_class] if multiple_field else ref_class
            pm.meta[field_name] = Field(label=field_label, schema='itemref',
                                        formtype='hidden', control='input',
                                        auto=False, atomic=False,
                                        optional=optional_field, multiple=multiple_field)
        else: # atom class
            atom = atom_map[field_type]
            if atom.convert: pm.cmap[field_name] = atom.convert
            if atom.display: pm.dmap[field_name] = atom.display
            if atom.read:    pm.rmap[field_name] = atom.read
            if atom.write:   pm.wmap[field_name] = atom.write
            if atom.query:   pm.qmap[field_name] = atom.query
            if multiple_field:
                pm.empty[field_name] = [] if optional_field else [atom.default]
            elif not optional_field:
                pm.empty[field_name] = atom.default
            if not optional_field:
                pm.empty[field_name] = [] if multiple_field else atom.default
            pm.schema[schema_key] = [atom.schema] if multiple_field else atom.schema
            pm.meta[field_name] = Field(label=field_label, schema=field_type,
                                        formtype=atom.formtype, control=atom.control,
                                        enum=atom.enum, auto=auto_field,
                                        optional=optional_field, multiple=multiple_field)
    return pm

def read_models(model_defs):
    """Read model definitions from 'model' section of configuration file.

    Read model definitions from 'model' section of configuration file (YAML), and
    dynamically create subclasses of the parent class Item. The parent class
    depends on the storage engine, so this is determined by the configuration file.
    The 'model' section is a dict, with key=class name, and value=list of fields

    Note: do not set class attributes that shadow a dictionary method, e.g. 'keys'.
    Class attribute 'index' is allowed, since it is a sequence method.

    Arguments:
        model_defs (list): list of model definitions.

    Returns:
        None: adds parsed models to global variable' models'.
    """
    if setting.config['dbtype'] == 'mongodb':
        from .engine.mongodb import Item
    elif setting.config['dbtype'] == 'rethinkdb':
        from .engine.rethinkdb import Item
    else:
        raise InternalError('Storage engine should be MongoDB or RethinkDB')
    setting.models['BareItem'] = BareItem
    setting.models['Item'] = Item

    model_names = [name for name in model_defs.keys() if name[0].isalpha()]
    # build reference classes (unless they already exist)
    for model_name in model_names:
        ref_name = model_name+'Ref'
        ref_class = type(ref_name, (ItemRef,), {})
        ref_class.collection = model_name
        if ref_name not in setting.models:
            setting.models[ref_name] = ref_class
    # build actual (outer) classes
    for model_name in model_names:
        model_def = model_defs[model_name]
        class_dict = {}
        pm = parse_model_def(model_def, model_defs) # pm: instance of class ParsedModel
        pm.names.extend(Item.fields)
        index = BareItem.index.copy()
        index.extend(pm.index)
        schema = BareItem.schema.copy()
        schema.update(pm.schema)
        meta = BareItem.meta.copy()
        meta.update(pm.meta)
        empty = BareItem._empty.copy() # shallow copy, but that is sufficient here
        empty.update(pm.empty)
        pm.cmap.update(BareItem.cmap)
        pm.dmap.update(BareItem.dmap)
        pm.qmap.update(BareItem.qmap)
        pm.rmap.update(BareItem.rmap)
        pm.wmap.update(BareItem.wmap)
        class_dict['name']      = model_name
        class_dict['index']     = index
        class_dict['cmap']      = pm.cmap
        class_dict['dmap']      = pm.dmap
        class_dict['rmap']      = pm.rmap
        class_dict['wmap']      = pm.wmap
        class_dict['qmap']      = pm.qmap
        class_dict['fields']    = pm.names
        class_dict['_empty']    = empty
        class_dict['schema']   = schema
        class_dict['_format']   = pm.fmt
        class_dict['meta']      = meta
        class_dict['_validate'] = Schema(schema, required=True, extra=True)
        model_class = type(model_name, (Item,), class_dict)
        model_class.create_collection()
        model_class.create_index(index)
        setting.models[model_name] = model_class
