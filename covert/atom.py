# -*- coding: utf-8 -*-
"""
covert.atom
-----
Objects and functions related to the atomic constituents of items.
"""

from datetime import datetime, date, time
from operator import itemgetter
from collections import OrderedDict

# Atom = namedtuple('Atom', ['schema', 'convert', 'display'])
class Atom(tuple):
    __slots__ = ()
    def __new__(cls, schema, convert, display):
        return tuple.__new__(cls, (schema, convert, display))
    def __repr__(self):
        return 'Atom(schema=%r, convert=%r, display=%r)' % self
    schema  = property(itemgetter(0), doc='field number 0')
    convert = property(itemgetter(1), doc='field number 1')
    display = property(itemgetter(2), doc='field number 2')

atom_map = {}
def register_atom(name, **kwarg):
    if name in atom_map:
        raise Exception('Atom {0} is already registered'.format(name))
    else:
        atom_map[name] = Atom(**kwarg)

true_strings = ('j', 'y', 'ja', 'yes')
bool_repr = {True:'ja', False:'nee'}
# identity = lambda value: value # when we use dense/full transformation maps
identity = None # when we use sparse transformation maps (faster)

register_atom('boolean',
    schema  = type(True),
    convert = lambda value: value.lower() in true_strings,
    display = lambda value: bool_repr[value]
)

register_atom('date',
    schema  = date,
    convert = lambda value: datetime.strptime(value, "%Y-%m-%d"),
    display = lambda value: datetime.strftime(value, "%Y-%m-%d")
)

register_atom('datetime',
    schema  = datetime,
    convert = lambda value: datetime.strptime(value, "%Y-%m-%d_%H:%M:%S"),
    display = lambda value: datetime.strftime(value, "%Y-%m-%d_%H:%M:%S")
)

register_atom('float',
    schema  = float,
    convert = lambda value: float(value),
    display = lambda value: '{0:.2}'.format(value)
)

register_atom('integer',
    schema  = int,
    convert = lambda value: int(value),
    display = lambda value: str(value)
)

register_atom('memo',
    schema  = str,
    convert = identity,
    display = identity
)

register_atom('string',
    schema  = str,
    convert = identity,
    display = identity
)

register_atom('text',
    schema  = str,
    convert = identity,
    display = identity
)

register_atom('time',
    schema  = time,
    convert = lambda value: datetime.strptime(value, "%H:%M:%S"),
    display = lambda value: datetime.strftime(value, "%H:%M:%S")
)

register_atom('url',
    schema  = str,
    convert = identity,
    display = identity
)
