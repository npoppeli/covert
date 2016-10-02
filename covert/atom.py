# -*- coding: utf-8 -*-
"""
covert.atom
-----
Objects and functions related to the atomic constituents of items.
Ideally, this should be a common subset of MongoDB, RethinkDB and ArangoDB.

TODO: Atoms have a partial dependence on the storage engine, namely via the read and write maps.
"""

from datetime import datetime, date, time
from operator import itemgetter
from .common import Error

class Atom:
    __slots__ = ('schema', 'convert', 'display', 'formtype', 'control', 'read', 'write', 'enum')
    def __init__(self, schema, convert, display, formtype, control, read=None, write=None, enum=None):
        self.schema   = schema
        self.convert  = convert
        self.display  = display
        self.formtype = formtype
        self.control  = control
        self.read     = read
        self.write    = write
        self.enum     = enum

atom_map = {}
def register_atom(name, **kwarg):
    if name in atom_map:
        raise Error('Atom {0} is already registered'.format(name))
    else:
        atom_map[name] = Atom(**kwarg)

true_strings = ('j', 'ja') # TODO: I18N
# EN: yes/no or y/n, SV: ja/nej
bool_repr = {True:'ja', False:'nee'}   # TODO: I18N
# identity = lambda x: x # when we use dense/full transformation maps
identity = None # when we use sparse transformation maps (faster)

register_atom('boolean',
    schema   = bool,
    convert  = lambda value: value.lower() in true_strings,
    display  = lambda value: bool_repr[value],
    formtype = 'boolean',
    enum     = ['nee', 'ja'],
    control  = 'radio'
)

# date and datetime use str.format in the display maps, to avoid Python issue 13305
midnight = time(0, 0, 0, 0)
register_atom('date',
    schema   = date,
    convert  = lambda value: datetime.strptime(value, "%Y-%m-%d"),
    display  = lambda value: '{0:04d}-{1:02d}-{2:02d}'.format(value.year, value.month, value.day),
    read     = lambda value: value.date(),
    write    = lambda value: datetime.combine(value, midnight),
    formtype = 'date',
    control  = 'input'
)

register_atom('datetime',
    schema   = datetime,
    convert  = lambda value: datetime.strptime(value, "%Y-%m-%dT%H:%M:%S"),
    display  = lambda value: '{0:04d}-{1:02d}-{2:02d}T{3:02d}:{4:02d}:{5:02d}'.\
               format(value.year, value.month, value.day, value.hour, value.minute, value.second),
    formtype = 'datetime',
    control  = 'input'
)

register_atom('float',
    schema   = float,
    convert  = float,
    display  = lambda value: '{0:.2}'.format(value),
    formtype = 'number',
    control  = 'input'
)

genders = ['?', 'v', 'm'] # TODO: I18N
register_atom('gender', # TODO: add possibility to define this in application
    schema   = int,
    convert  = int,
    display  = lambda value: genders[value],
    formtype = 'gender',
    control  = 'radio',
    enum     = genders
)

register_atom('integer',
    schema   = int,
    convert  = int,
    display  = str,
    formtype = 'number',
    control  = 'input'
)

register_atom('memo',
    schema   = str,
    convert  = identity,
    display  = identity,
    formtype = 'memo',
    control  = 'textarea'
)

register_atom('string',
    schema   = str,
    convert  = identity,
    display  = identity,
    formtype = 'text',
    control  = 'input'
)

register_atom('text',
    schema   = str,
    convert  = identity,
    display  = identity,
    formtype = 'text',
    control  = 'textarea'
)

register_atom('time',
    schema   = time,
    convert  = lambda value: datetime.strptime(value, "%H:%M:%S"),
    display  = lambda value: '{0:02d}:{1:02d}:{2:02d}'.format(value.hour, value.minute, value.second),
    formtype = 'datetime',
    control  = 'input'
)

register_atom('url',
    schema   = str,
    convert  = identity,
    display  = identity,
    formtype = 'url',
    control  = 'input'
)
