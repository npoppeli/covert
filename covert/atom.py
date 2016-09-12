# -*- coding: utf-8 -*-
"""
covert.atom
-----
Objects and functions related to the atomic constituents of items.

TODO: Atoms have a partial dependence on the storage engine, namely via the read and write maps.
"""

from datetime import datetime, date, time
from operator import itemgetter
from .common import Error

# Atom = namedtuple('Atom', ['sname', 'schema', 'convert', 'display', 'read', 'write', 'form'])
class Atom(tuple):
    __slots__ = ()
    def __new__(cls, schema, convert, display, read=None, write=None, form=None):
        return tuple.__new__(cls, (schema, convert, display, read, write, form))
    def __repr__(self):
        return 'Atom(schema=%r, convert=%r, display=%r, read=%r, write=%r, form=%r)' % self
    schema  = property(itemgetter(0))
    convert = property(itemgetter(1))
    display = property(itemgetter(2))
    read    = property(itemgetter(3))
    write   = property(itemgetter(4))
    form    = property(itemgetter(5))

atom_map = {}
def register_atom(name, **kwarg):
    if name in atom_map:
        raise Error('Atom {0} is already registered'.format(name))
    else:
        atom_map[name] = Atom(**kwarg)

true_strings = ('j', 'y', 'ja', 'yes') # TODO: I18N
bool_repr = {True:'ja', False:'nee'}   # TODO: I18N
# identity = lambda x: x # when we use dense/full transformation maps
identity = None # when we use sparse transformation maps (faster)

register_atom('boolean',
    schema  = bool,
    convert = lambda value: value.lower() in true_strings,
    display = lambda value: bool_repr[value],
    form    = {'type': 'boolean', 'range': ['nee', 'ja'], 'control':'radio'}
)

# date and datetime have new display maps, to avoid Python issue 13305
midnight = time(0, 0, 0, 0)
register_atom('date',
    schema  = date,
    convert = lambda value: datetime.strptime(value, "%Y-%m-%d"),
    display = lambda value: '{0:04d}-{1:02d}-{2:02d}'.format(value.year, value.month, value.day),
    read    = lambda value: value.date(),
    write   = lambda value: datetime.combine(value, midnight),
    form    = {'type': 'date', 'control': 'input'}
)

register_atom('datetime',
    schema  = datetime,
    convert = lambda value: datetime.strptime(value, "%Y-%m-%dT%H:%M:%S"),
    display = lambda value: '{0:04d}-{1:02d}-{2:02d}T{3:02d}:{4:02d}:{5:02d}'.\
              format(value.year, value.month, value.day, value.hour, value.minute, value.second),
    form    = {'type': 'datetime', 'control': 'input'}
)

register_atom('float',
    schema  = float,
    convert = float,
    display = lambda value: '{0:.2}'.format(value),
    form    = {'type': 'number', 'control': 'input'}
)

genders = ['?', 'v', 'm'] # TODO: I18N
register_atom('gender', # TODO: add possibility to define this in application
    schema  = int,
    convert = lambda value: genders.index(value),
    display = lambda value: genders[value],
    form    = {'type': 'gender', 'control': 'radio', 'range':genders}
)

register_atom('integer',
    schema  = int,
    convert = int,
    display = str,
    form    = {'type': 'number', 'control': 'input'}
)

register_atom('memo',
    schema  = str,
    convert = identity,
    display = identity,
    form    = {'type': 'memo', 'control': 'textarea'}
)

register_atom('string',
    schema  = str,
    convert = identity,
    display = identity,
    form    = {'type': 'text', 'control': 'input'}
)

register_atom('text',
    schema  = str,
    convert = identity,
    display = identity,
    form    = {'type': 'text', 'control': 'textarea'}
)

register_atom('time',
    schema  = time,
    convert = lambda value: datetime.strptime(value, "%H:%M:%S"),
    display = lambda value: '{0:02d}:{1:02d}:{2:02d}'.format(value.hour, value.minute, value.second),
    form    = {'type': 'datetime', 'control': 'input'}
)

register_atom('url',
    schema  = str,
    convert = identity,
    display = identity,
    form    = {'type': 'url', 'control': 'input'}
)
