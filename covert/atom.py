# -*- coding: utf-8 -*-
"""Objects and functions related to the atomic constituents of items.

The atomic constituents of items should be a common subset of MongoDB, RethinkDB and ArangoDB.
Otherwise, atoms have a partial dependence on the storage engine, via the read and write maps.

ISO 8601 datetime notation:
* date    : yyyy-mm-dd
* time    : hh:mm:ss
* datetime: <date>T<time>
"""

from datetime import datetime, date, time
from .common import InternalError, escape_squote
# from . import common as c
# use c._ for translation

class Atom:
    """Instances of this class define the atomic constituents of items.

    Each item stored in the database is built from atoms or atomic constituents.
    The standard atoms are: integer, float, boolean, date, time, datetime and text (3 types).
    Applications can define extra atoms with define_atom().

    Attributes:
        * see constructor method
    """

    __slots__ = ('schema', 'convert', 'display', 'query', 'formtype', 'control',
                 'default', 'read', 'write', 'enum', 'expr')

    def __init__(self, schema, convert, display, query, formtype, control,
                 default='', read=None, write=None, enum=None, expr=None):
        """Initialize atom.

        Arguments:
            schema   (class):    class of atom, used for item validation
            convert  (callable): convert string representation to actual type
            query    (callable): similar to convert, adds search operator
            display  (callable): convert to string representation
            formtype (str):      HTML form type
            enum     (list):     range of allowed values for enumerated type
            control  (str):      HTML input type
        """
        self.schema   = schema
        self.convert  = convert
        self.display  = display
        self.query    = query
        self.expr     = expr
        self.formtype = formtype
        self.control  = control
        self.default  = default
        self.read     = read
        self.write    = write
        self.enum     = enum


atom_map = {}
def define_atom(name, **kwarg):
    """Define new type of atom.

    Arguments:
        name  (str): name of atom type
    """
    if name in atom_map:
        raise InternalError(_('Atom {0} is already registered').format(name))
    else:
        atom_map[name] = Atom(**kwarg)

identity = None # since we use sparse transformation maps

MINYEAR        = 1401 # restriction in RethinkDB
EMPTY_DATETIME = datetime(MINYEAR, 1, 1, 0, 0, 0)
EMPTY_TIME     = time(0, 0, 0)
EMPTY_DATE     = date(MINYEAR, 1, 1)
MIDNIGHT       = time(0, 0, 0, 0)

true_strings = ('j', 'ja')
# TODO I18N EN: yes/no or y/n, SV: ja/nej
bool_repr = {True:'ja', False:'nee'}

boolean_convert = lambda x: bool(int(x))
define_atom('boolean',
            schema   = bool,
            convert  = boolean_convert,
            query    = lambda x: ('==', boolean_convert(x)),
            display  = lambda x: bool_repr[x],
            default  = False,
            formtype = 'boolean',
            enum     = ['nee', 'ja'],
            control  = 'radio'
            )

# date and datetime use str.format in the display map, to avoid Python issue 13305
def date_convert(x):
    return datetime.strptime(x, "%Y-%m-%d").date() if x else EMPTY_DATE

def date_display(x):
    return '????-??-??' if x.year == MINYEAR\
    else '{0:04d}-{1:02d}-{2:02d}'.format(x.year, x.month, x.day)

def date_expr(x):
    return "'" + date_display(x) + "'"

def datetime_display(x):
    return '{0:04d}-{1:02d}-{2:02d}T{3:02d}:{4:02d}:{5:02d}'.\
      format(x.year, x.month, x.day, x.hour, x.minute, x.second)

def datetime_expr(x):
    return "'" + datetime_display(x) + "'"

def str_display(x):
    return "'" + escape_squote(x) + "'"

define_atom('date',
            schema   = date,
            convert  = date_convert,
            display  = date_display,
            query    = lambda x: ('==', date_convert(x)),
            expr     = date_expr,
            read     = lambda x: x.date(),
            write    = lambda x: datetime.combine(x, MIDNIGHT),
            default  = EMPTY_DATE,
            formtype = 'date',
            control  = 'input'
            )

def datetime_convert(x):
    return datetime.strptime(x, "%Y-%m-%dT%H:%M:%S") if x else EMPTY_DATETIME

define_atom('datetime',
            schema   = datetime,
            convert  = datetime_convert,
            display  = datetime_display,
            query    = lambda x: ('==', datetime_convert(x)),
            expr     = datetime_expr,
            default  = EMPTY_DATETIME,
            formtype = 'datetime',
            control  = 'input'
            )

define_atom('float',
            schema   = float,
            convert  = float,
            display  = lambda x: '{0:.2}'.format(x),
            query    = lambda x: ('==', float(x)),
            expr     = str,
            default  = 0.0,
            formtype = 'number',
            control  = 'input'
            )

define_atom('integer',
            schema   = int,
            convert  = int,
            display  = str,
            query    = lambda x: ('==', int(x)),
            expr     = str,
            default  = 0,
            formtype = 'number',
            control  = 'input'
            )

define_atom('memo',
            schema   = str,
            convert  = identity,
            display  = identity,
            query    = lambda x: ('%', x),
            expr     = str_display,
            default  = '',
            formtype = 'memo',
            control  = 'textarea'
            )

define_atom('string',
            schema   = str,
            convert  = identity,
            display  = identity,
            query    = lambda x: ('%', x),
            expr     = str_display,
            default  = '',
            formtype = 'text',
            control  = 'input'
            )

define_atom('text',
            schema   = str,
            convert  = identity,
            display  = identity,
            query    = lambda x: ('%', x),
            expr     = str_display,
            default  = '',
            formtype = 'text',
            control  = 'textarea'
            )

def time_convert(x):
    return datetime.strptime(x, "%H:%M:%S")

def time_display(x):
    return '{0:02d}:{1:02d}:{2:02d}'.format(x.hour, x.minute, x.second)

def time_expr(x):
    return "'" + time_display(x) + "'"

define_atom('time',
            schema   = time,
            convert  = time_convert,
            display  = time_display,
            query    = lambda x: ('==', time_convert(x)),
            expr     = time_display,
            default  = EMPTY_TIME,
            formtype = 'datetime',
            control  = 'input'
            )

define_atom('url',
            schema   = str,
            convert  = identity,
            display  = identity,
            query    = lambda x: ('=~', x),
            expr     = str_display,
            default  = '',
            formtype = 'url',
            control  = 'input'
            )
