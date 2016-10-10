# -*- coding: utf-8 -*-
"""
covert.atom
-----
Objects and functions related to the atomic constituents of items.
This should be a common subset of MongoDB, RethinkDB and ArangoDB. Otherwise, atoms
have a partial dependence on the storage engine, via the read and write maps.
"""

from datetime import datetime, date, time, MINYEAR
from .common import Error

class Atom:
    __slots__ = ('schema', 'convert', 'display', 'query', 'formtype', 'control',
                 'default', 'read', 'write', 'enum')
    def __init__(self, schema, convert, display, query, formtype, control,
                 default='', read=None, write=None, enum=None):
        self.schema   = schema
        self.convert  = convert
        self.display  = display
        self.query    = query
        self.formtype = formtype
        self.control  = control
        self.default  = default
        self.read     = read
        self.write    = write
        self.enum     = enum

atom_map = {}
def register_atom(name, **kwarg):
    if name in atom_map:
        raise Error('Atom {0} is already registered'.format(name))
    else:
        atom_map[name] = Atom(**kwarg)

EMPTY_DATETIME = datetime(MINYEAR, 1, 1, 0, 0, 0)
EMPTY_TIME     = time(0, 0, 0)
EMPTY_DATE     = date(MINYEAR, 1, 1)
MIDNIGHT       = time(0, 0, 0, 0)

true_strings = ('j', 'ja') # TODO: I18N
# EN: yes/no or y/n, SV: ja/nej
bool_repr = {True:'ja', False:'nee'}   # TODO: I18N

# Tree transformations are a cornerstone of the framework. There are two types
# of transformation maps: (1) dense or full maps, where every node has a mapping function,
# possibly the identity, or (2) spare maps, where a node has a mapping function only
# when necessary (other nodes get mapping function=None). Performance measurements
# show that option 2 is faster.
identity = None # since we use sparse transformation maps

# Query transformations use 2-tuples and 3-tuples. The first member of the tuple is
# a 2-character operator: == for equal, =~ for regex match (Perl5 influence in a Python application),
# [] for 'between boundaries (boundaries included)' etcetera.

boolean_convert = lambda value: value.lower() in true_strings,
register_atom('boolean',
    schema   = bool,
    convert  = boolean_convert,
    query    = lambda value: ('==', boolean_convert(value)),
    display  = lambda value: bool_repr[value],
    formtype = 'boolean',
    enum     = ['nee', 'ja'],
    control  = 'radio'
)

# date and datetime use str.format in the display maps, to avoid Python issue 13305
date_convert = lambda value: datetime.strptime(value, "%Y-%m-%d")
register_atom('date',
    schema   = date,
    convert  = date_convert,
    display  = lambda value: '{0:04d}-{1:02d}-{2:02d}'.format(value.year, value.month, value.day),
    query    = lambda value: ('==', date_convert(value)),
    read     = lambda value: value.date(),
    write    = lambda value: datetime.combine(value, MIDNIGHT),
    default  = EMPTY_DATE,
    formtype = 'date',
    control  = 'input'
)

datetime_convert =lambda value: datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
register_atom('datetime',
    schema   = datetime,
    convert  = datetime_convert,
    display  = lambda value: '{0:04d}-{1:02d}-{2:02d}T{3:02d}:{4:02d}:{5:02d}'.\
               format(value.year, value.month, value.day, value.hour, value.minute, value.second),
    query    = lambda value: ('==', datetime_convert(value)),
    default  = EMPTY_DATETIME,
    formtype = 'datetime',
    control  = 'input'
)

register_atom('float',
    schema   = float,
    convert  = float,
    display  = lambda value: '{0:.2}'.format(value),
    query    = lambda value: ('==', float(value)),
    formtype = 'number',
    control  = 'input'
)

genders = ['?', 'v', 'm'] # TODO: I18N
register_atom('gender', # TODO: add possibility to define this in application
    schema   = int,
    convert  = int,
    display  = lambda value: genders[value],
    query    = lambda value: ('==', int(value)),
    formtype = 'gender',
    control  = 'radio',
    default  = 0,
    enum     = genders
)

register_atom('integer',
    schema   = int,
    convert  = int,
    display  = str,
    query    = lambda value: ('==', int(value)),
    formtype = 'number',
    control  = 'input'
)

register_atom('memo',
    schema   = str,
    convert  = identity,
    display  = identity,
    query    = lambda value: ('=~', value),
    formtype = 'memo',
    control  = 'textarea'
)

register_atom('string',
    schema   = str,
    convert  = identity,
    display  = identity,
    query    = lambda value: ('=~', value),
    formtype = 'text',
    control  = 'input'
)

register_atom('text',
    schema   = str,
    convert  = identity,
    display  = identity,
    query    = lambda value: ('=~', value),
    formtype = 'text',
    control  = 'textarea'
)

time_convert = lambda value: datetime.strptime(value, "%H:%M:%S")
register_atom('time',
    schema   = time,
    convert  = time_convert,
    display  = lambda value: '{0:02d}:{1:02d}:{2:02d}'.format(value.hour, value.minute, value.second),
    query    = lambda value: ('==', time_convert(value)),
    default  = EMPTY_TIME,
    formtype = 'datetime',
    control  = 'input'
)

register_atom('url',
    schema   = str,
    convert  = identity,
    display  = identity,
    query    = lambda value: ('=~', value),
    formtype = 'url',
    control  = 'input'
)
