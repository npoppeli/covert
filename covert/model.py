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

As of August 2019 we use a new approach for mapping between the application structure of a document and
a flattened structure of the same document that is used to create, e.g., an HTML representation.

The new mapping is bijective, i.e. completely retains the structure of the document, including
types of scalars and the order in lists.

The flat structure is an ordered dictionary, where each value is a string representation of the
value in the original document, and each key is a compact description of the path of that value
in the original document. The 'display' transformation maps from the application structure to the
flat structure.

Each key has the following structure: [field].[sequence_number].[atom_type](#[index])?, where
* 'field' is the field name from the model definition
* 'sequence_number' is the number of the dictionary in the application structure,
  starting at 0 for the outermost dictionary
* 'atom_type' is a one-character code that describes the type of the value, either
  - a code from the atom map
  - 'a' for empty array
  - 'z' for None
  - '^' for item reference
  - 'o' followed by one or more digits, indicating a nested dictionary
 * 'index' is a list index, in case of a list-valued (multiple) field

The 'convert' transformation takes the flattened version of a document and rebuilds the original
application structure of the document.

This algorithm is based on work by Paul van Schayck (Maastricht UMC), Ton Smeele (Utrecht University),
Daniel Theunissen (Maastricht University) and Lazlo Westerhof (Utrecht University) on JSON-AVU
mapping for iRODS. Original code can be found here:
https://github.com/MaastrichtUniversity/irods_avu_json.
"""

from copy import deepcopy
import gettext, re
from os.path import join, realpath
from collections import OrderedDict
# Schema validation with voluptuous:
# - PREVENT_EXTRA (0): prevent additional keys in the data, raise error MultipleInvalid (default)
# - ALLOW_EXTRA   (1): allow additional keys in the data
# - REMOVE_EXTRA  (2): remove additional keys from the data
from voluptuous import Schema, Optional, MultipleInvalid, ALLOW_EXTRA, PREVENT_EXTRA
try:
    from jsondiff import diff as json_diff
except ImportError:
    """Define a bare-bones implementation of json_diff"""
    def json_diff(a, b, **kwargs):
        ka, kb = set(a.keys()), set(b.keys())
        inserted, deleted, updated = {}, {}, {}
        for k in ka | kb:
            va, vb = a.get(k, None), b.get(k, None)
            if isinstance(va, dict) or isinstance(vb, dict) or \
               isinstance(va, list) or isinstance(vb, list): continue
            if   va and not vb: deleted[k]  = va
            elif vb and not va: inserted[k] = vb
            elif va != vb:      updated[k]  = vb
        result = {}
        if inserted: result['$insert'] = inserted
        if deleted:  result['$delete'] = deleted
        if updated:  result['$update'] = updated
        return result

from .atom import atom_map, EMPTY_DATETIME, atom_codemap
from .common import InternalError, SUCCESS, FAIL, logger, show_document
from .controller import exception_report
from .event import event
from . import common as c
from . import setting

def mapdoc(fnmap, doc):
    """Map item (document) by applying functions in function map.

    Map item (dictionary) by applying the functions in the function map 'fnmap'.
    The keys of this map are the field names for a particular model. The function
    maps are sparse, i.e. do not contain mapping functions for every field in the model.
    Missing mapping functions are implied to be the identity function.

    Arguments:
        fnmap (dict): dictionary of mapping functions.
        doc   (dict):   item to be mapped (transformed).

    Returns:
        dict: transformed item (document).
    """
    result = {}
    try:
        for key, value in doc.items():
            if key in fnmap: # apply mapping function
                if fnmap[key] is None:
                    continue
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
    except TypeError as e:
        logger.debug("\nmapdoc generated a TypeError:\n{}\n".\
                     format(str(e), show_document(doc)))
        return {}

class Field:
    """Meta-data for one field in an item.

    The meta-data of a field (component of an item) are derived from the atom and model definitions.

    Attributes:
        * see constructor method
    """
    __slots__ = ('label', 'schema', 'formtype', 'code', 'control', 'optional', 'multiple',
                 'auto', 'atomic',  'control', 'enum')
    def __init__(self, label, schema, formtype, code, optional=False, multiple=False,
                 control='input', auto=False, atomic=True, enum=None):
        """Initialize object.

        Arguments:
            label    (str):   human-readable description of field
            schema   (class): class of atom, used for item validation
            formtype (str):   HTML form type
            code     (str):   one-character atom code
            control  (str):   HTML input type
            enum     (list):  range of allowed values for enumerated type
            optional (bool):  True if field is optional
            multiple (bool):  True if field is multiple (list)
            auto     (bool):  True if field is automatic
            atomic   (bool):  True if field is atomic
        """
        self.label    = label
        self.schema   = schema
        self.formtype = formtype
        self.code     = code
        self.control  = control
        self.optional = optional
        self.multiple = multiple
        self.auto     = auto
        self.atomic   = atomic
        self.enum     = enum

bool_atom     = atom_map['boolean']
string_atom   = atom_map['string']
datetime_atom = atom_map['datetime']

RE_PATH  = '^(_?[a-zA-Z]+)\.(\d+)\.([^o]|o\d+)(#\d+)?'

def format_item(item):
    """Default format function for Item"""
    return item._format.format(**item)

# I18N: this list is needless, but helps us get the labels in the I18N framework
bareitem_labels = [c._('Sort by'), c._('Created'), c._('Modified'), c._('Active')]

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
    _format = 'Item {id}'
    _formatter = format_item
    name = 'BareItem'
    fields = ['id', '_skey', 'ctime', 'mtime', 'active']
    index = [('id', 1), ('_skey', 1)]
    # validation
    schema    = {'id':string_atom.schema, '_skey': string_atom.schema, 'active': bool_atom.schema,
                 'ctime':datetime_atom.schema, 'mtime':datetime_atom.schema}
    _validate = None
    _empty    = {'id':'', '_skey': '', 'active':True,
                 'ctime':EMPTY_DATETIME, 'mtime':EMPTY_DATETIME}
    # transformation maps
    cmap = {'ctime': datetime_atom.convert, 'mtime': datetime_atom.convert, 'active': bool_atom.convert}
    dmap = {'ctime': datetime_atom.display, 'mtime': datetime_atom.display, 'active': bool_atom.display}
    qmap = {'ctime':datetime_atom.query,    'mtime':datetime_atom.query,    'active': bool_atom.query,
            '_skey': string_atom.query}
    emap = {'ctime':datetime_atom.expr,     'mtime':datetime_atom.expr,     'active': bool_atom.expr,
            '_skey': string_atom.expr}
    rmap = {}
    wmap = {}
    # metadata
    meta = OrderedDict()
    meta['id']     = Field(label='Id',       code='s', schema='string',  formtype='hidden',  auto=True)
    meta['_skey']  = Field(label='Sort by',  code='s', schema='string',  formtype='hidden',  auto=True)
    meta['active'] = Field(label='Active',   code='b', schema='boolean', formtype='boolean', auto=False,
                           enum=bool_atom.enum, control=bool_atom.control)
    meta['ctime']  = Field(label='Created',  code='x', schema='datetime', formtype='hidden', auto=True)
    meta['mtime']  = Field(label='Modified', code='x', schema='datetime', formtype='hidden', auto=True)

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
                logger.error(c._('Error in applying rmap to doc=%s\n%s'),
                             doc, exception_report(e, ashtml=False))

    def accept(self, visitor):
        visitor.visit(self)

    @classmethod
    def convert(cls, doc, partial=False):
        """Convert a document in flat structure to a document in application structure,
        or a partial document, i.e. a dictionary, depending on the parameter `partial`.

        Arguments:
            * doc     (OrderedDict): flattened document
            * partial (bool)       : partial or full document?

        Returns:
            instance of current class, or dictionary
        """
        result = cls._convert(doc, 0)
        if partial:
            return result
        else:
            doc = cls()
            doc.update(result)
            return doc

    @classmethod
    def _convert(cls, doc, parent):
        """
        Auxiliary method. This does the actual conversion of a flattened structure, but
        creates a regular dictionary, not yet an Item instance.

        Arguments:
            doc    (OrderedDict): flattened document
            parent (int)        : number of parent dictionary

        Returns:
            dictionary
        """
        result = {}
        for key in sorted(doc.keys()):
            value = doc[key]
            # check if the key matches the pattern, and if so unpack it
            # groups: 1=field name, 2: object number, 3: atom code | object id, 4: array index
            pattern = re.compile(RE_PATH)
            matched = pattern.match(key)
            if not matched:
                result[key] = value
                continue
            field = matched.group(1)
            if matched.group(2):
                object_number = int(matched.group(2))
            else:
                object_number = None
            if object_number != parent:
                continue
            atom_type = matched.group(3)
            list_index = matched.group(4)
            if list_index:
                list_index = int(list_index[1:])
            # convert value, depending on field 3 in the key (atom type)
            if atom_type.startswith('o'):  # nested dictionary
                value = cls._convert(doc, int(atom_type[1:]))
            elif atom_type == 'z':
                value = None
            elif atom_type == 'a':
                value = []
            elif atom_type == '^':  # item reference
                ref_classname, object_id = value[-1].split('.')
                ref_class = setting.models[ref_classname]
                value = ref_class(None if object_id == '0' else object_id)
            elif atom_type in atom_codemap:  # scalar value
                convert = atom_codemap[atom_type].convert
                if convert is not None:
                    value = convert(value)
            # add value to dictionary in progress, where necessary as element of a list
            if list_index is not None and field not in result:
                result[field] = []
            if field in result and isinstance(result[field], list):
                result[field].insert(list_index, value)
            else:
                result[field] = value
        return result

    def copy(self):
        """Make deep copy of item.

        Make deep copy of item, erasing the 'auto' fields, so that it looks new.

        Returns:
            Item: copy of item with 'auto' fields set to 'None'.
        """
        cls = self.__class__
        item = cls()
        clone = deepcopy(self)
        for name in cls.fields:
            if cls.meta[name].auto:
                clone[name] = None
        item.update(clone)
        return item

    def display(self):
        """Convert a document in application structure to one in a flat structure.

        Returns:
            OrderedDict
        """
        self._display = []
        self._dict_number = 0
        self._display_dict(self, 0)
        return OrderedDict(self._display)

    def _display_dict(self, dct, parent, index=''):
        # process dictionary in model order
        declared_keys = [key for key in self.fields if key in dct.keys()]
        extra_keys = [key for key in dct.keys() if key not in self.fields]
        for key in declared_keys + extra_keys:
            value = dct[key]
            # treat extra keys the same way as keys declared in the model,
            # with two exceptions: value is a list or value is a dictionary
            if key in extra_keys and (isinstance(value, list) or isinstance(value, dict)):
                self._display.append((key, value))
            elif isinstance(value, dict):
                self._dict_number += 1
                object_label = 'o'+str(self._dict_number)
                self._display.append(('{}.{}.o{}{}'.\
                              format(key, parent, self._dict_number, index), object_label))
                self._display_dict(value, self._dict_number)
            elif value is None:
                self._display.append(('{}.{}.{}'.format(key, parent, 'z'), ''))
            elif isinstance(value, list):
                if value:
                    self._display_list(key, value, parent, index)
                else:
                    self._display.append(('{}.{}.{}'.format(key, parent, 'a'), ''))
            else: # scalar
                # atom type 's' implies cmap == dmap == identity
                code = self.meta[key].code if key in self.meta else 's'
                self._display.append(('{}.{}.{}'.format(key, parent, code),
                                     self.dmap[key](value) if key in self.dmap else value))

    def _display_list(self, key, lst, parent, index=''):
        if isinstance(lst[0], dict): # list of dictionaries, involves recursion
            for n, value in enumerate(lst):
                new_index = '{}#{}'.format(index, n)
                self._dict_number += 1
                self._display.append(('{}.{}.o{}{}'.format(key, parent, self._dict_number, new_index),
                                      'o'+str(self._dict_number)))
                self._display_dict(value, self._dict_number, new_index)
        else: # list of scalars
            # atom type 's' implies cmap == dmap == identity
            code = self.meta[key].code if key in self.meta else 's'
            for n, value in enumerate(lst):
                new_index = '{}#{}'.format(index, n)
                self._display.append(('{}.{}.{}{}'.format(key, parent, code, new_index),
                                     self.dmap[key](value) if key in self.dmap else value))

    def follow(self, key):
        """Retrieve item(s) referenced by itemref field from storage.

        Returns:
            Item  : item, if not multiple field
            [Item]: list of items, if multiple field
            None  : all other cases
        """
        if key in self.fields:
            meta = self.meta[key]
            if meta.schema == 'itemref':
                return [r.lookup() for r in self[key]] if meta.multiple else \
                        self[key].lookup()
            else:
                return None
        else:
            return None

    @classmethod
    def lookup(cls, oid):
        """Retrieve item with id=oid from storage.

        This is a trivial implementation, overridden by sub-classes.

        Arguments:
            * oid (str): item id.
        """
        item = {'id': oid}
        return cls(item)

    def take(self, *arg):
        """Retrieve item(s) referenced by itemref field from storage.
           Use case 1: item.take('key', value)
           Use case 2: item.take('refkey', 'key', value)

        Returns:
            list of scalars: when 2 arguments are given
            [Item]         : when 3 arguments are given
            None           : all other cases
        """
        if len(arg) == 2:
            key, value = arg[0], arg[1]
            if not (key in self and self.meta[key].multiple):
                return None
            if callable(value):
                return [v for v in self[key] if value(v)]
            else:
                return [v for v in self[key] if v == value]
        elif len(arg) == 3:
            refkey, key, value = arg[0], arg[1], arg[2]
            if refkey not in self:
                return None
            meta = self.meta[refkey]
            if not (meta.multiple and meta.schema == 'itemref'):
                return None
            referred = self.follow(refkey)
            if callable(value):
                return [r for r in referred if value(r[key])]
            else:
                return [r for r in referred if r[key] == value]
        else:
            return None

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
            _result = validator(doc)
            return {'status': SUCCESS, 'data': ''}
        except MultipleInvalid as e:
            error = '; '.join([str(el) for el in e.errors ])
            return {'status': FAIL, 'data': error}

    @classmethod
    def validation(cls, level):
        """Set validation level.

        Arguments:
            * level (str): validation level.
        """
        if level == 'strict':
            cls._validate.extra = PREVENT_EXTRA
        else:
            cls._validate.extra = ALLOW_EXTRA

    def __repr__(self):
        """Formal string representation of item.

        Returns:
            str: representation for Python interpreter.
        """
        content = ', '.join(["'{}':'{}'".format(key, self.get(key, '')) for key in self.fields])
        return '{}({})'.format(self.__class__.__name__, content)

    @classmethod
    def format_with(cls, func):
        cls._formatter = func

    def __str__(self):
        """Informal string representation of item.

        Returns:
            str: human-readable representation.
        """
        return self._formatter()

    def __xor__(self, other):
        """Compute difference between two Item instances.

        Returns:
              dict: dictionary with differences; keys are '$insert', '$update', '$delete'
        """
        diff = json_diff(self, other, syntax='explicit')
        result = {}
        ignore = [f for f in self.fields if self.meta[f].auto]
        for key, value in diff.items():
            details = {k: v for k, v in value.items() if k not in ignore}
            if str(key) in ('$insert', '$update', '$delete'):
                result[str(key)] = details
        return result

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
        (tuple): display presentation of item reference.
    """
    return ref.display()

def empty_reference(ref):
    """Check if ref is a logically empty ItemRef instance.

    Arguments:
        ref (itemref): item reference.

    Returns:
        (boolean): True if empty item reference.
    """
    return isinstance(ref, ItemRef) and not bool(ref)


class ItemRef:
    """Reference to Item"""
    collection = 'Item'
    name       = 'ItemRef'

    def __init__(self, refid=None):
        """Initialize item reference.

        This method is used as the read map for an item reference.

        Arguments:
            refid (str): id of item (default: None, for an empty reference).
        """
        self.pre = ''
        self.post = ''
        self.refid = refid
        self.str = ''

    def display(self):
        """Display form of item reference.

        Returns:
            (str, str, str, str, str): prefix, infix, URL, postfix, class+id.
        """
        if self.refid is None:
            return '', '', '#', '', \
                   '{}.0'.format(self.__class__.__name__)
        model = setting.models[self.collection]
        item = model.lookup(self.refid)
        event('display:pre', self, None)
        if item is None:
            return '', '', '#', '', \
                   '{}.0'.format(self.__class__.__name__)
        else:
            return self.pre, \
                   str(item), \
                   '/{}/{}'.format(self.collection.lower(), self.refid), \
                   self.post, \
                   '{}.{}'.format(self.__class__.__name__, self.refid)

    def lookup(self, field=None):
        """Retrieve item referenced by itemref object from storage.
        Return entire item if field is None, else only the field `field`.

        Returns:
            - if field is None: item retrieved from storage, None if non-existent
            - otherwise: one field from this item
        """
        model = setting.models[self.collection]
        item = model.lookup(self.refid)
        if item:
            return item.get(field, None) if field else item
        else:
            return None

    def __bool__(self):
        """Determine truth value of item reference.

        Returns:
            bool: self.id is not-empty (True)
        """
        return bool(self.refid)

    def __eq__(self, other):
        """Determine equality of item references.

        Returns:
            bool: self == other.
        """
        return self.__class__.__name__ == other.__class__.__name__ and \
               self.refid == other.refid

    def __hash__(self):
        """Calculate hash value.

        Returns:
            int: hash value of self.refid.
        """
        return self.refid.__hash__()

    def __ne__(self, other):
        """Determine inequality of item references.

        Returns:
            bool: self != other.
        """
        return self.__class__.__name__ != other.__class__.__name__ or \
               self.refid != other.refid

    def __repr__(self):
        """Formal string representation of item reference.

        Returns:
            str: representation for Python interpreter.
        """
        return "{}({},{})".format(self.__class__.__name__, self.collection, self.refid)

    def __str__(self):
        """Informal string representation of item reference.

        Returns:
            str: human-readable representation.
        """
        return "{}.{}".format(self.collection, self.refid)


# Auxiliary classes: Visitor
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


# Model parsing
class ParsedModel:
    """Result of parsing a model definition.

    Attributes:
        names  (list):        field names
        index  (list):        indexed fields
        fmt    (str):         format string for string representation
        meta   (OrderedDict): meta-data
        empty  (dict):        empty item
        schema (dict):        schema for validation
        cmap   (dict):        convert map
        dmap   (dict):        display map
        rmap   (dict):        read map
        wmap   (dict):        write map, associated with read map
        qmap   (dict):        query map
        emap   (dict):        expression map, associated with query map
    """

    def __init__(self):
        """Construct parsed model definition."""
        self.names, self.index = [], []
        self.fmt = ''
        self.meta = OrderedDict()
        self.empty = {}
        self.schema = {}
        self.rmap, self.wmap = {}, {}
        self.dmap, self.cmap = {}, {}
        self.qmap, self.emap = {}, {}

def parse_model_def(model_def, model_defs, transl):
    """Parse definition of one model.

    Arguments:
        model_def (dict):  model definition to be parsed
        model_defs (list): list of all model definitions
                           (needed for forward references to inner classes)
    """
    pm = ParsedModel() # parsed model definition
    for line in model_def:
        field_def = line.split()
        if len(field_def) not in (3, 4):
            raise InternalError(c._("Field definition '{0}' should have 3 or 4 components").format(line))
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
        field_label = transl(field_label.replace('_', ' '))
        if field_type[0] == '_': # embedded model (comparable to inner class)
            embedded = parse_model_def(model_defs[field_type], model_defs, transl)
            if multiple_field:
                pm.empty[field_name] = [embedded.empty] # if not optional_field else []
            elif not optional_field:
                pm.empty[field_name] = embedded.empty
            pm.schema[schema_key] = [embedded.schema] if multiple_field else embedded.schema
            pm.meta[field_name] = Field(label=field_label, schema='dict',
                                        formtype='dict', control='input',
                                        auto=False, atomic=False, code='_',
                                        optional=optional_field, multiple=multiple_field)
            pm.names.extend(embedded.names)
            pm.cmap[field_name] = dict
            pm.dmap[field_name] = dict
            pm.rmap[field_name] = dict
            pm.wmap[field_name] = dict
            pm.qmap[field_name] = '=='
            pm.emap[field_name] = None
            pm.cmap.update(embedded.cmap)
            pm.dmap.update(embedded.dmap)
            pm.rmap.update(embedded.rmap)
            pm.wmap.update(embedded.wmap)
            pm.qmap.update(embedded.qmap)
            pm.emap.update(embedded.emap)
            for name in embedded.names: # necessary for preserving order
                pm.meta[name] = embedded.meta[name]
        elif field_type[0] == '^': # reference to model
            ref_name = field_type[1:]+'Ref'
            ref_class = setting.models[ref_name]
            if ref_name not in setting.models:
                raise InternalError(c._("Reference to unknown model '{0}' in {1}").format(ref_name, line))
            pm.dmap[field_name] = display_reference
            pm.rmap[field_name] = ref_class
            pm.wmap[field_name] = get_objectid
            pm.qmap[field_name] = None
            pm.emap[field_name] = None
            empty_ref = ref_class(None)
            if multiple_field:
                pm.empty[field_name] = [] if optional_field else [empty_ref]
            elif not optional_field:
                pm.empty[field_name] = empty_ref
            pm.schema[schema_key] = [ref_class] if multiple_field else ref_class
            pm.meta[field_name] = Field(label=field_label, schema='itemref',
                                        formtype='hidden', control='input',
                                        auto=False, atomic=False, code='^',
                                        optional=optional_field, multiple=multiple_field)
        else: # atom class
            atom = atom_map[field_type]
            if atom.convert: pm.cmap[field_name] = atom.convert
            if atom.display: pm.dmap[field_name] = atom.display
            if atom.read:    pm.rmap[field_name] = atom.read
            if atom.write:   pm.wmap[field_name] = atom.write
            if atom.query:   pm.qmap[field_name] = atom.query
            if atom.expr:    pm.emap[field_name] = atom.expr
            if multiple_field:
                pm.empty[field_name] = [] if optional_field else [atom.default]
            elif not optional_field:
                pm.empty[field_name] = atom.default
            if not optional_field:
                pm.empty[field_name] = [] if multiple_field else atom.default
            pm.schema[schema_key] = [atom.schema] if multiple_field else atom.schema
            pm.meta[field_name] = Field(label=field_label, schema=field_type,
                                        formtype=atom.formtype, control=atom.control,
                                        enum=atom.enum, auto=auto_field, code=atom.code,
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
        raise InternalError(c._('Storage engine should be MongoDB or RethinkDB'))
    setting.models['BareItem'] = BareItem
    setting.models['Item'] = Item

    # I18N: find the message catalog (.mo) for the model
    locale_dir = realpath(join(setting.site, 'locales'))
    model_trans = gettext.translation('model', localedir=locale_dir, languages=[setting.language])
    model_names = [name for name in model_defs.keys() if name[0].isalpha()]
    # I18N: translate the labels of the BareItem model
    for key in BareItem.fields:
        BareItem.meta[key].label = c._(BareItem.meta[key].label)
    # construct reference classes
    for model_name in model_names:
        ref_name = model_name+'Ref'
        ref_class = type(ref_name, (ItemRef,), {})
        ref_class.collection = model_name
        ref_class.name       = ref_name
        setting.models[ref_name] = ref_class
    # construct actual (outer) classes
    for model_name in model_names:
        model_def = model_defs[model_name]
        class_dict = {}
        pm = parse_model_def(model_def, model_defs, model_trans.gettext)
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
        pm.emap.update(BareItem.emap)
        pm.rmap.update(BareItem.rmap)
        pm.wmap.update(BareItem.wmap)
        class_dict['name']    = model_name
        class_dict['index']   = index
        class_dict['cmap']    = pm.cmap
        class_dict['dmap']    = pm.dmap
        class_dict['rmap']    = pm.rmap
        class_dict['wmap']    = pm.wmap
        class_dict['qmap']    = pm.qmap
        class_dict['emap']    = pm.emap
        class_dict['fields']  = pm.names
        class_dict['_empty']  = empty
        class_dict['schema']  = schema
        class_dict['_format'] = pm.fmt
        class_dict['meta']    = meta
        # Note: the way we define validation here does not forbid extra fields, because
        # # we need e.g. '_id' and '_rev'. This creates the risk of unwanted fields in
        # the database. The application must check for this.
        class_dict['_validate'] = Schema(schema, required=True, extra=ALLOW_EXTRA)
        model_class = type(model_name, (Item,), class_dict)
        model_class.create_collection()
        model_class.create_index(index)
        setting.models[model_name] = model_class
