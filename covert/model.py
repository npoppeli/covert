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

from copy import deepcopy
from collections import OrderedDict
from operator import itemgetter
from voluptuous import Schema, Optional, MultipleInvalid
from .atom import atom_map
from .common import Error
from . import setting

def mapdoc(fnmap, doc, inner=False):
    """mapdoc(doc) -> newdoc
       Map doc using functions in fnmap
    """
    newdoc = {}
    for key, value in doc.items():
        if key in fnmap: # apply mapping function
            if isinstance(value, dict): # embedded document
                newdoc[key] = mapdoc(fnmap, value, inner=True)
            elif isinstance(value, list): # list of scalars or documents
                if len(value) == 0: # empty list
                    newdoc[key] = []
                elif isinstance(value[0], dict): # list of documents
                    newdoc[key] = [mapdoc(fnmap, element, inner=True) for element in value]
                else: # list of scalars
                    newdoc[key] = [fnmap[key](element) for element in value]
            else: # scalar
                newdoc[key] = fnmap[key](value)
        else: # no mapping for this element
            newdoc[key] = value
    return newdoc

# Field = namedtuple('Field', ['label', 'schema', 'optional', 'multiple', 'hidden', 'auto'])
class Field(tuple):
    __slots__ = ()
    def __new__(cls, label, schema, optional=False, multiple=False, hidden=False, auto=False):
        return tuple.__new__(cls, (label, schema, optional, multiple, hidden, auto))
    def __repr__(self):
        return 'Field(label=%r, schema=%r, optional=%r, multiple=%r, hidden=%r, auto=%r)' % self
    label    = property(itemgetter(0))
    schema   = property(itemgetter(1))
    optional = property(itemgetter(2))
    multiple = property(itemgetter(3))
    hidden   = property(itemgetter(4))
    auto     = property(itemgetter(5))

class ParsedModel():
    """ParsedModel: result of parsing model definition."""
    def __init__(self):
        self.names, self.index = [], []
        self.fmt = ''
        self.skeleton = OrderedDict()
        self.empty = {}
        self.schema, self.qschema = {}, {}
        self.rmap, self.wmap, self.dmap, self.cmap = {}, {}, {}, {}

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
        - id     string     @%  _Id
        - ctime  datetime    %   Created
        - mtime  datetime    %   Modified
        - active boolean     %  _Active
    """
    ba = atom_map['boolean']
    sa = atom_map['string']
    da = atom_map['datetime']
    name = 'BareItem'
    # all, all mutable, and all short fields
    fields  = ['id', 'ctime', 'mtime', 'active']
    mfields = []
    sfields = ['ctime', 'mtime', 'active']
    # schemata for normal and query validation
    _schema  = {'id':sa.schema, 'ctime':da.schema, 'mtime':da.schema, 'active': ba.schema}
    _qschema = {}
    # transformation maps
    cmap  = {'ctime':da.convert, 'mtime':da.convert, 'active': ba.convert}
    dmap  = {'ctime':da.display, 'mtime':da.display, 'active': ba.display}
    rmap = {}
    wmap = {}
    # skeleton
    skeleton = OrderedDict()
    skeleton['id']     = Field(label='Id',       schema='string',   auto=True, hidden=True )
    skeleton['ctime']  = Field(label='Created',  schema='datetime', auto=True, hidden=False)
    skeleton['mtime']  = Field(label='Modified', schema='datetime', auto=True, hidden=False)
    skeleton['active'] = Field(label='Active',   schema='boolean',  auto=True, hidden=True )

    def __init__(self, doc=None):
        """
        __init__(self, doc)
        Create new instance, initialize from 'doc' (if available).
        """
        super().__init__()
        for field in self.fields:
            self[field] = [] if field in self.skeleton[field].multiple else None
        if doc:
            self.update(mapdoc(self._rmap, doc))

    _format = 'Item {id}'
    def __str__(self):
        return self._format.format(self)

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
            # error = dict([('.'.join(el.path), el.msg) for el in e.errors ])
            error = str(e.errors)
            return {'ok': False, 'error':error }

    @classmethod
    def lookup(cls, oid):
        """
        lookup(cls, oid): doc
        Return trivial item (method is redefined in Item class)
        oid: object id (string)
        """
        doc = {'id':oid}
        return cls(doc)

    @classmethod
    def empty(cls):
        """
        empty(cls): doc
        Create new item from empty document for this class
        """
        return cls(cls._empty)
        
    @classmethod
    def convert(cls, doc):
        """
        convert(cls, doc): newdoc
        Convert stringified item to item with typed fields.
        """
        return mapdoc(cls._cmap, doc)

    def display(self, doc):
        """
        display(cls, doc): newdoc
        Convert item with typed fields to item with stringified fields.
        """
        return mapdoc(self._dmap, doc)

    def copy(self):
        """
        copy(self): newdoc
        Make deep copy of document, erasing the 'auto' fields, so that it looks new.
        """
        cls = self.__class__
        newdoc = deepcopy(self)
        for name in cls.fields:
            if cls.skeleton[name].auto:
                newdoc[name] = None
        return cls(newdoc)

class ItemRef:
    collection = 'Item'
    def __init__(self, objectid):
        self.id = objectid
        self.str = ''
    def __str__(self):
        return self.__repr__()
    def __repr__(self):
        return "{}({} {})".format(self.__class__.__name__, self.collection, self.id)

def get_objectid(ref):
    return ref.id

def set_str_field(ref):
    model = setting.models[ref.collection]
    item = model.lookup(ref.id)
    ref.str = str(item)
    return ref
    
def parse_model_def(model_def, model_defs):
    """parse definition of one model"""
    pm = ParsedModel() # parsed model definition
    for line in model_def:
        field_def = line.split()
        if len(field_def) not in (3, 4):
            raise Error("field definition '{0}' should have 3 or 4 components".format(line))
        optional_field, multiple_field = False, False
        if len(field_def) == 3:
            field_name, field_type, field_label = field_def
        else: # n == 4
            field_name, field_type, field_card, field_label = field_def
            multiple_field = field_card in '+*'
            optional_field = field_card in '?*'
            # indexed field: < >
            if field_card in '<>':
                direction = -1 if field_card == '<' else 1
                pm.index.append( (field_name, direction) )
        if field_name == '_format':
            pm.fmt = field_label
            continue
        schema_key = Optional(field_name) if optional_field else field_name
        pm.names.append(field_name)
        field_hidden = field_label == '_'
        if not field_hidden:
            field_label = field_label.replace('_', ' ')
        if field_type[0] == '_': # embedded model (comparable to inner class)
            embedded = parse_model_def(model_defs[field_type], model_defs)
            pm.empty[field_name] = [ embedded.empty ] if multiple_field else embedded.empty
            pm.qschema[field_name] = embedded.qschema
            pm.schema[schema_key] = [ embedded.schema ] if multiple_field else embedded.schema
            pm.skeleton[field_name] = Field(label=field_label, schema='dict',
                                         hidden=field_hidden, auto=False,
                                         optional=optional_field, multiple=multiple_field)
            pm.names.extend(embedded.names)
            pm.cmap[field_name] = dict
            pm.dmap[field_name] = dict
            pm.rmap[field_name] = dict
            pm.wmap[field_name] = dict
            pm.cmap.update(embedded.cmap)
            pm.dmap.update(embedded.dmap)
            pm.rmap.update(embedded.rmap)
            pm.wmap.update(embedded.wmap)
            for name in embedded.names: # necessary for preserving order
                pm.skeleton[name] = embedded.skeleton[name]
        elif field_type[0] == '^': # reference to model
            ref_name = field_type[1:]+'Ref'
            if ref_name not in setting.models:
                raise Error("reference to unknown model '{0}' in {1}".format(ref_name, line))
            # don't add entry to pm.cmap, since conversion is unnecessary
            pm.dmap[field_name] = set_str_field # set itemref.str to str(item)
            pm.rmap[field_name] = setting.models[ref_name] # create ItemRef instance with argument 'objectid'
            pm.wmap[field_name] = get_objectid # write only objectid to database
            pm.empty[field_name] = [ None ] if multiple_field else None
            pm.qschema[field_name] = None
            pm.schema[schema_key] = [ setting.models[ref_name] ] if multiple_field else setting.models[ref_name]
            pm.skeleton[field_name] = Field(label=field_label, schema=ref_name,
                                            hidden=field_hidden, auto=False,
                                            optional=optional_field, multiple=multiple_field)
        else: # atom class
            atom = atom_map[field_type]
            if atom.convert: pm.cmap[field_name] = atom.convert
            if atom.display: pm.dmap[field_name] = atom.display
            if atom.read:    pm.rmap[field_name] = atom.read
            if atom.write:   pm.wmap[field_name] = atom.write
            pm.empty[field_name] = [ None ] if multiple_field else None
            pm.qschema[field_name] = atom.schema
            pm.schema[schema_key]  = [ atom.schema ] if multiple_field else atom.schema
            pm.skeleton[field_name] = Field(label=field_label, schema=field_type,
                                            hidden=field_hidden, auto=False,
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
        mutable_fields = [f for f in pm.names
                          if not (pm.skeleton[f].hidden or pm.skeleton[f].auto)]
        mutable_fields.extend(Item.mfields)
        short_fields = [f for f in pm.names
                        if not (pm.skeleton[f].multiple or pm.skeleton[f].schema in ('text', 'memo'))]
        short_fields.extend(Item.sfields)
        pm.names.extend(Item.fields)
        class_dict['index'].extend(pm.index)
        schema = Item._schema.copy()
        schema.update(pm.schema)
        qschema = Item._qschema.copy()
        qschema.update(pm.qschema)
        skeleton = Item.skeleton.copy()
        skeleton.update(pm.skeleton)
        pm.cmap.update(Item.cmap)
        pm.dmap.update(Item.dmap)
        pm.rmap.update(Item.rmap)
        pm.wmap.update(Item.wmap)
        class_dict['name']       = model_name
        class_dict['cmap']       = pm.cmap
        class_dict['dmap']       = pm.dmap
        class_dict['rmap']       = pm.rmap
        class_dict['wmap']       = pm.wmap
        class_dict['fields']     = pm.names
        class_dict['mfields']    = mutable_fields
        class_dict['sfields']    = short_fields
        class_dict['_empty']     = pm.empty
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
