# -*- coding: utf-8 -*-
"""
covert.model
-----
Objects and functions related to models. A model defines the structure
of an item.

A basic item is a simple dictionary. A more complicated item can also
contain lists and dictionaries. This is fully recursive.  Instead of
embedding a basic item of class B inside an item of class A, you can
also add references to items of class B inside an item of class A
('linking'). A reference to an item is essentially a 3-tuple (collection
name, item id, string representation). The third item is dynamically computed
upon using the item reference.

storage -> [JSON document] -> read -> [item] -> display -> [item stringified] -> HTML page
HTML form -> [item stringified] -> convert -> [item] -> write -> [JSON document] -> storage

TODO:
- embedding and linking in show panels
- embedding and linking in form panels
- tools (JS) for adding, modifying and deleting item references
- tools (JS) for adding, modifying and deleting sub-items
"""

from bisect import bisect_left, bisect_right
from copy import deepcopy
from collections import OrderedDict
from voluptuous import Schema, Optional, MultipleInvalid
from .atom import atom_map, EMPTY_DATETIME
from .common import Error
from . import setting

def _flatten(doc, prefix, keys):
    for key in [key for key in keys if key in doc.keys()]:  # keys in model order
        value = doc[key]
        sub_prefix = '{}{}.'.format(prefix, key)
        if isinstance(value, dict):  # embedded document
            yield from _flatten(value, sub_prefix, keys)
        elif isinstance(value, list):  # list of scalars or documents
            if len(value) == 0:  # empty list
                yield sub_prefix + '0', ''
            elif isinstance(value[0], dict):  # list of documents
                for sub_key, element in enumerate(value):
                    yield from _flatten(element, sub_prefix+str(sub_key)+'.', keys)
            else:  # list of scalars
                for sub_key, element in enumerate(value):
                    yield sub_prefix + str(sub_key), element
        else:  # scalar
            yield prefix + key, value

def prune(doc, depth):
    """prune(doc) -> newdoc
       Prune a flattened document to given depth, where depth = key.count('.')
    """
    return OrderedDict((key, value) for (key, value) in doc.items() if key.count('.') <= depth)

def unflatten(doc):
    """unflatten(doc) -> newdoc
       Unflatten document to (re)create hierarchical structure.
       A flattened document has keys 'a' or 'a.b'. As preparation, the keys are
       transformed into lists (25% faster than keeping them as strings), and
       the document is transformed to a list of 2-tuples, sorted on key.
    """
    list_rep = [(key.split('.'), doc[key]) for key in sorted(doc.keys())]
    return _unflatten(list_rep)

def _unflatten(list_rep):
    newdoc = {}
    car_list = [elt[0].pop(0) for elt in list_rep]  # take first element (car) from each key
    car_set = set(car_list)  # set of (unique) car's is the set of keys of newdoc
    for key in car_set:
        begin = bisect_left(car_list, key)
        end = bisect_right(car_list, key)
        children = list_rep[begin:end]
        if len(children) == 1:
            # We can distinguish 3 cases: 1. cdr is ['0']; 2. cdr is empty;
            # 3. cdr is [a] where a is some string, but this is unrealistic.
            child = children[0]
            newdoc[key] = [child[1]] if child[0] == ['0'] else child[1]  # scalar
        else:
            newdoc[key] = _unflatten(children)
    if all([key.isnumeric() for key in car_set]):  # turn dict with numeric keys into list
        return [t[1] for t in sorted(newdoc.items(), key=lambda t: int(t[0]))]
    else:
        return newdoc

def mapdoc(fnmap, doc):
    """mapdoc(doc) -> newdoc
       Map doc using functions in fnmap
    """
    newdoc = {}
    for key, value in doc.items():
        if key in fnmap: # apply mapping function
            if isinstance(value, dict): # embedded document
                newdoc[key] = mapdoc(fnmap, value)
            elif isinstance(value, list): # list of scalars or documents
                if len(value) == 0: # empty list
                    newdoc[key] = []
                elif isinstance(value[0], dict): # list of documents
                    newdoc[key] = [mapdoc(fnmap, element) for element in value]
                else: # list of scalars
                    newdoc[key] = [fnmap[key](element) for element in value]
            else: # scalar
                # print('>> mapdoc: key={} value={}'.format(key, value))
                newdoc[key] = fnmap[key](value)
        else: # no mapping for this element
            newdoc[key] = value
    return newdoc

# Atom defines: 'schema', 'convert', 'display', 'formtype', 'control', 'read', 'write', 'enum'
# schema: used for Item._schema, for validation purposes
# formtype, control, enum: used for UI metadata, supplemented by label

class Field:
    __slots__ = ('label', 'schema', 'formtype', 'control', 'optional', 'multiple',
                 'hidden', 'auto', 'atomic',  'control', 'enum')
    def __init__(self, label, schema, formtype, optional=False, multiple=False,
                 control='input', hidden=False, auto=False, atomic=True, enum=None):
        self.label    = label
        self.schema   = schema
        self.formtype = formtype
        self.control  = control
        self.optional = optional
        self.multiple = multiple
        self.hidden   = hidden
        self.auto     = auto
        self.atomic   = atomic
        self.enum     = enum

class ParsedModel:
    """ParsedModel: result of parsing model definition."""
    def __init__(self):
        self.names, self.index = [], []
        self.fmt = ''
        self.skeleton = OrderedDict()
        self.empty = {}
        self.schema, self.qschema = {}, {}
        self.rmap, self.wmap, self.dmap, self.cmap, self.qmap = {}, {}, {}, {}, {}

# Document revisions
# 1. If the number of revisions is low, keep all of them in the storage,
#    and mark one of them as active.
# 2. Otherwise, keep only the active revision in the item storage, and store
#    backward deltas in a separate storage (use libdiff for text).

class BareItem(dict):
    """
    BareItem: base class for Item.
    This class defines common data attributes and storage-independent methods.
    model (%=auto):
      BareItem:
        - id     string    % _Id
        - ctime  datetime  %  Created
        - mtime  datetime  %  Modified
        - active boolean   % _Active
    """
    ba = atom_map['boolean']
    sa = atom_map['string']
    da = atom_map['datetime']
    name = 'BareItem'
    fields  = ['id', 'ctime', 'mtime', 'active']
    # schemata for normal and query validation
    _schema  = {'id':sa.schema, 'ctime':da.schema, 'mtime':da.schema, 'active': ba.schema}
    _qschema = {}
    _empty   = {'id':'', 'ctime':EMPTY_DATETIME, 'mtime':EMPTY_DATETIME, 'active':True}
    # transformation maps
    cmap  = {'ctime':da.convert, 'mtime':da.convert, 'active': ba.convert}
    dmap  = {'ctime':da.display, 'mtime':da.display, 'active': ba.display}
    rmap = {}
    wmap = {}
    # skeleton
    skeleton = OrderedDict()
    # TODO: labels should become language-dependent
    # TODO: 'active' is not auto, but has a default (True)
    skeleton['id']     = Field(label='Id',       schema='string',   formtype='hidden',  auto=True,  hidden=True )
    skeleton['ctime']  = Field(label='Created',  schema='datetime', formtype='hidden',  auto=True,  hidden=False)
    skeleton['mtime']  = Field(label='Modified', schema='datetime', formtype='hidden',  auto=True,  hidden=False)
    skeleton['active'] = Field(label='Actief',   schema='boolean',  formtype='boolean', auto=False, hidden=False )

    def __init__(self, doc=None):
        """
        __init__(self, doc)
        Create new item, initialize from 'doc' (if available).
        """
        super().__init__()
        for field in self.fields:
            self[field] = [] if self.skeleton[field].multiple else None
        if doc:
            self.update(mapdoc(self.rmap, doc))

    @classmethod
    def empty(cls):
        """
        empty(cls): item
        Create new empty item
        """
        item = cls()
        item.update(cls._empty)
        return item

    _format = 'Item {id}'
    def __str__(self):
        return self._format.format(**self)

    def __repr__(self):
        content = ', '.join(["'{}':'{}'".format(key, self.get(key, '')) for key in self.fields])
        return '{}({})'.format(self.__class__.__name__, content)

    @classmethod
    def validate(cls, doc, kind=''):
        """
        validate(cls, doc): result
        Validate document and return
        - {'ok': True, error:{} } if validation OK
        - {'ok': False, error:{field1:error1, ...} } if validation not OK
        Class method: allows validation of search queries and items fresh from the storage.
        """
        validator = cls._qvalidate if kind == 'query' else cls._validate
        try:
            _ = validator(doc)
            return {'ok': True, 'error':{} }
        except MultipleInvalid as e:
            error = '; '.join([str(el) for el in e.errors ])
            # error = str(e.errors)
            return {'ok': False, 'error':error }

    @classmethod
    def lookup(cls, oid):
        """
        lookup(cls, oid): item
        Return trivial item (method is redefined in Item class)
        oid: object id (string)
        """
        doc = {'id':oid}
        return cls(doc)

    @classmethod
    def convert(cls, doc):
        """
        convert(cls, doc): item
        Convert item with only string values to item with typed values.
        """
        item = cls()
        item.update(mapdoc(cls.cmap, doc))
        return item

    def display(self):
        """
        display(self): newitem
        Convert item with typed values to item with only string values.
        """
        cls = self.__class__
        item = cls()
        item.update(mapdoc(self.dmap, self))
        return item

    def flatten(self):
        """flatten(self) -> dict
           Flatten item (document with hierarchical structure) to flat dictionary.
        """
        flat_dict = OrderedDict()
        for key, value in _flatten(self, '', self.fields):
            flat_dict[key] = value
        return flat_dict

    def copy(self):
        """
        copy(self): newitem
        Make deep copy of item, erasing the 'auto' fields, so that it looks new.
        """
        cls = self.__class__
        item = cls()
        clone = deepcopy(self)
        for name in cls.fields:
            if cls.skeleton[name].auto:
                clone[name] = None
        item.update(clone)
        return item

class ItemRef:
    collection = 'Item'
    def __init__(self, objectid):
        self.id = objectid
        self.str = ''
    def __str__(self):
        return self.__repr__()
    def __repr__(self):
        return "{}({}, {})".format(self.__class__.__name__, self.collection, self.id)

def get_objectid(ref):
    return ref.id

def ref_tuple(ref):
    if ref.id is None:
        return '', ''
    else:
        model = setting.models[ref.collection]
        item = model.lookup(ref.id)
        return str(item), '/{}/{}'.format(ref.collection.lower(), ref.id) # label, url
    
def parse_model_def(model_def, model_defs):
    """parse definition of one model"""
    pm = ParsedModel() # parsed model definition
    label_index = setting.languages.index(setting.language)
    for line in model_def:
        field_def = line.split()
        if len(field_def) not in (3, 4):
            raise Error("field definition '{0}' should have 3 or 4 components".format(line))
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
        field_hidden = field_label.startswith('_')
        if not field_hidden:
            field_label = field_label.replace('_', ' ')
        parts = field_label.split('|')
        field_label = parts[label_index]
        if field_type[0] == '_': # embedded model (comparable to inner class)
            embedded = parse_model_def(model_defs[field_type], model_defs)
            pm.empty[field_name] = [ embedded.empty ] if multiple_field else embedded.empty
            pm.qschema[field_name] = embedded.qschema
            pm.schema[schema_key] = [ embedded.schema ] if multiple_field else embedded.schema
            pm.skeleton[field_name] = Field(label=field_label, schema='dict',
                                            formtype='hidden', control='input',
                                            hidden=field_hidden, auto=False, atomic=False,
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
                pm.skeleton[name] = embedded.skeleton[name]
        elif field_type[0] == '^': # reference to model
            ref_name = field_type[1:]+'Ref'
            ref_class = setting.models[ref_name]
            if ref_name not in setting.models:
                raise Error("reference to unknown model '{0}' in {1}".format(ref_name, line))
            # don not extend pm.cmap, since model reference needs no conversion
            pm.dmap[field_name] = ref_tuple # create tuple (label, url)
            pm.rmap[field_name] = ref_class # create ItemRef instance with argument 'objectid'
            pm.wmap[field_name] = get_objectid # write only object id to database
            pm.qmap[field_name] = None
            empty_ref = ref_class(None)
            pm.empty[field_name] = [] if multiple_field else empty_ref
            pm.qschema[field_name] = None
            pm.schema[schema_key] = [ ref_class ] if multiple_field else ref_class
            pm.skeleton[field_name] = Field(label=field_label, schema=ref_name,
                                            formtype='hidden', control='input',
                                            hidden=field_hidden, auto=False, atomic=False,
                                            optional=optional_field, multiple=multiple_field)
        else: # atom class
            atom = atom_map[field_type]
            if atom.convert: pm.cmap[field_name] = atom.convert
            if atom.display: pm.dmap[field_name] = atom.display
            if atom.read:    pm.rmap[field_name] = atom.read
            if atom.write:   pm.wmap[field_name] = atom.write
            if atom.query:   pm.qmap[field_name] = atom.query
            pm.empty[field_name] = [] if multiple_field else atom.default
            pm.qschema[field_name] = atom.schema
            pm.schema[schema_key]  = [ atom.schema ] if multiple_field else atom.schema
            pm.skeleton[field_name] = Field(label=field_label, schema=field_type,
                                            formtype=atom.formtype, control=atom.control,
                                            enum=atom.enum, hidden=field_hidden, auto=auto_field,
                                            optional=optional_field, multiple=multiple_field)
    return pm

def read_models(model_defs):
    """
    Read model definitions from 'model' section of configuration file (YAML), and
    dynamically create subclasses of the parent class Item. The parent class
    depends on the storage engine, so this is determined by the configuration file.
    The 'model' section is a dict, with key=class name, and value=list of fields

    Note: do not set class attributes that shadow a dictionary method, e.g. 'keys'.
    Class attribute 'index' is allowed, since it is a sequence method.
    """
    if setting.config['dbtype'] == 'mongodb':
        from .engine.mongodb import Item
    elif setting.config['dbtype'] == 'rethinkdb':
        from .engine.rethinkdb import Item
    else:
        raise Error('Storage engine should be MongoDB or RethinkDB')
    setting.models['BareItem'] = BareItem
    setting.models['Item'] = Item

    model_names = [name for name in model_defs.keys() if name[0].isalpha()]
    for model_name in model_names: # build reference classes
        ref_name = model_name+'Ref'
        ref_class = type(ref_name, (ItemRef,), {})
        ref_class.collection = model_name
        setting.models[ref_name] = ref_class
    for model_name in model_names: # build actual (outer) classes
        model_def, class_dict = model_defs[model_name], {}
        class_dict['index'] = [ ('id', 1) ]
        pm = parse_model_def(model_def, model_defs) # pm: instance of class ParsedModel
        pm.names.extend(Item.fields)
        class_dict['index'].extend(pm.index)
        schema = BareItem._schema.copy()
        schema.update(pm.schema)
        qschema = BareItem._qschema.copy()
        qschema.update(pm.qschema)
        skeleton = BareItem.skeleton.copy()
        skeleton.update(pm.skeleton)
        empty = BareItem._empty.copy()
        empty.update(pm.empty)
        pm.cmap.update(BareItem.cmap)
        pm.dmap.update(BareItem.dmap)
        pm.rmap.update(BareItem.rmap)
        pm.wmap.update(BareItem.wmap)
        class_dict['name']       = model_name
        class_dict['cmap']       = pm.cmap
        class_dict['dmap']       = pm.dmap
        class_dict['rmap']       = pm.rmap
        class_dict['wmap']       = pm.wmap
        class_dict['qmap']       = pm.qmap
        class_dict['fields']     = pm.names
        class_dict['_empty']     = empty
        class_dict['_schema']    = schema
        class_dict['_qschema']   = qschema
        class_dict['_format']    = pm.fmt
        class_dict['skeleton']   = skeleton
        class_dict['_validate']  = Schema(schema, required=True, extra=True)
        class_dict['_qvalidate'] = Schema(qschema)
        model_class = type(model_name, (Item,), class_dict)
        model_class.create_collection()
        model_class.create_index(class_dict['index'])
        setting.models[model_name] = model_class
