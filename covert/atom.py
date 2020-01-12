# -*- coding: utf-8 -*-
"""Objects and functions related to the atomic constituents of items.

The atomic constituents of items should be a common subset of MongoDB, RethinkDB and ArangoDB.
Otherwise, atoms have a partial dependence on the storage engine via the read and write maps.

ISO 8601 datetime notation:
* date    : yyyy-mm-dd
* time    : hh:mm:ss
* datetime: <date>T<time>
"""

from datetime import datetime, date, time
from .common import InternalError, escape_squote
from . import common as c

class Atom:
    """Instances of this class define the atomic constituents of items.

    Each item stored in the database is built from atoms or atomic constituents.
    The standard atoms are: integer, float, boolean, date, time, datetime and text (3 types).
    Applications can define extra atoms with define_atom().

    Attributes:
        * see constructor method
    """

    __slots__ = ('code', 'schema', 'convert', 'display', 'formtype', 'control',
                 'default', 'query', 'read', 'write', 'enum', 'expr')

    def __init__(self, code, schema, convert, display, formtype, control,
                 default='', query='==', read=None, write=None, enum=None, expr=None):
        """Initialize atom.

        Arguments:
            code     (str):      one-letter code for atom, used for (un)flattening
                                 lowercase letters are reserved for internal use
            schema   (class):    class of atom, used for item validation
            convert  (callable): convert string representation to actual type
            query    (str):      standard operator in queries (default: ==)
            expr     (str):      convert string representation to type used in query expression
            display  (callable): convert to string representation
            formtype (str):      HTML form input type
            enum     (list):     range of allowed values for enumerated type
            control  (str):      HTML form element (input, radio or textarea)
        """
        self.code     = code
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
atom_codemap = {}
def define_atom(name, **kwarg):
    """Define new type of atom.

    Arguments:
        name  (str): name of atom type
    """
    new_atom = Atom(**kwarg)
    if name in atom_map or new_atom.code in atom_codemap:
        raise InternalError(c._('Atom {0} is already registered').format(name))
    else:
        atom_map[name] = new_atom
        atom_codemap[new_atom.code] = new_atom

identity = None # since we use sparse transformation maps

MINYEAR        = 1401 # restriction in RethinkDB
EMPTY_DATETIME = datetime(MINYEAR, 1, 1, 0, 0, 0)
EMPTY_TIME     = time(0, 0, 0)
EMPTY_DATE     = date(MINYEAR, 1, 1)
MIDNIGHT       = time(0, 0, 0, 0)

def empty_scalar(a):
    return a == '' or a is None or a == 0 or \
           a == EMPTY_DATE or a == EMPTY_DATETIME or a == EMPTY_TIME

def empty_dict(d):
    return isinstance(d, dict) and not any(d.values())

def empty_list(l):
    if isinstance(l, list):
        return l == [] or (len(l) == 1 and (empty_scalar(l[0]) or empty_dict(l[0])))
    else:
        return False

true_strings = ('j', 'ja')
# TODO I18N EN: yes/no or y/n, SV: ja/nej
bool_repr = {True:'ja', False:'nee'}

boolean_convert = lambda x: bool(int(x))
define_atom('boolean',
            code     = 'b',
            schema   = bool,
            convert  = boolean_convert,
            display  = lambda x: bool_repr[x],
            default  = False,
            formtype = 'radio',
            enum     = ['nee', 'ja'],
            control  = 'radio'
            )

# date and datetime use str.format in the display map, to avoid Python issue 13305
def date_convert(x):
    if not x or x == '????-??-??':
        return EMPTY_DATE
    else:
        return datetime.strptime(x, "%Y-%m-%d").date()

def date_display(x):
    if x.year == MINYEAR:
        return '????-??-??'
    else:
        return '{0:04d}-{1:02d}-{2:02d}'.format(x.year, x.month, x.day)

def date_expr(x):
    return "'" + date_display(x) + "'"

define_atom('date',
            code     = 'd',
            schema   = date,
            convert  = date_convert,
            display  = date_display,
            expr     = date_expr,
            read     = lambda x: x.date(),
            write    = lambda x: datetime.combine(x, MIDNIGHT),
            default  = EMPTY_DATE,
            formtype = 'date',
            control  = 'input'
            )

def datetime_convert(x):
    if x:
        return datetime.strptime(x, "%Y-%m-%dT%H:%M:%S")
    else:
        return EMPTY_DATETIME

def datetime_display(x):
    return '{0:04d}-{1:02d}-{2:02d}T{3:02d}:{4:02d}:{5:02d}'.\
      format(x.year, x.month, x.day, x.hour, x.minute, x.second)

def datetime_expr(x):
    return "'" + datetime_display(x) + "'"

define_atom('datetime',
            code     = 'x',
            schema   = datetime,
            convert  = datetime_convert,
            display  = datetime_display,
            expr     = datetime_expr,
            default  = EMPTY_DATETIME,
            formtype = 'datetime',
            control  = 'input'
            )

define_atom('float',
            code     = 'f',
            schema   = float,
            convert  = float,
            display  = lambda x: '{0:.2}'.format(x),
            expr     = str,
            default  = 0.0,
            formtype = 'number',
            control  = 'input'
            )

define_atom('integer',
            code     = 'i',
            schema   = int,
            convert  = int,
            display  = str,
            expr     = str,
            default  = 0,
            formtype = 'number',
            control  = 'input'
            )

def str_display(x):
    return "'" + escape_squote(x) + "'"

define_atom('memo',
            code     = 'm',
            schema   = str,
            convert  = identity,
            display  = identity,
            query    = '%',
            expr     = str_display,
            default  = '',
            formtype = 'text',
            control  = 'textarea'
            )

define_atom('string',
            code     = 's',
            schema   = str,
            convert  = identity,
            display  = identity,
            query    = '%',
            expr     = str_display,
            default  = '',
            formtype = 'text',
            control  = 'input'
            )

define_atom('text',
            code     = 'q',
            schema   = str,
            convert  = identity,
            display  = identity,
            query    = '%',
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
            code     = 't',
            schema   = time,
            convert  = time_convert,
            display  = time_display,
            expr     = time_display,
            default  = EMPTY_TIME,
            formtype = 'datetime',
            control  = 'input'
            )

define_atom('url',
            code     = 'u',
            schema   = str,
            convert  = identity,
            display  = identity,
            query    = '%',
            expr     = str_display,
            default  = '',
            formtype = 'url',
            control  = 'input'
            )
