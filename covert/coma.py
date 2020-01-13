# -*- coding: utf-8 -*-
"""Objects and functions related to templates.

The layout of HTML pages, and HTML and XML fragments is specified by templates.
COvert's Mustache Analog (COMA) is a template engine that superficially resembles
Mustache and Handlebars but under the hood is quite different.

Conventions:
* loop handlers (e.g. each) put the repeat variables @0, @1, @2, ...,
  @first and @index in the context (local scope)
* templates that are used as macros have implicit arguments _0, _1, ...,
  which get their values from the argument list of the template root (global scope)
"""

import operator, re, string
from inspect import isfunction
from collections import UserList
from . import setting
# TODO: I18N from . import common as c
from .common import logger

multiple_newline = re.compile(r'\n *\n')
list_index = re.compile(r'\[\d+\]')

# various auxiliary functions
def abbrev(s):
    s0 = s.strip().replace('\n', ' ')
    return s0[0:50] + '...' if len(s0)>50 else s0

def short(context):
    return "{}".format(', '.join(context.keys()))

macro_parameter = re.compile(r'^_(?:\d)$')
repeat_variable = re.compile(r'^@(?:\d|index|first)$')

def get_value(path, context, root):
    """This function performs most of the magic of retrieving information
    to use in templates. Each path goes through a two-part expansion process:
    in the first part, macro parameters are expanded, and in the second
    part repeat variables are expanded.
    Path: an object of type UserList(str).
    """
    value = context
    path_1 = UserList()
    for part in path:
        if macro_parameter.match(part):
            step = root.args[part]
            if isinstance(step, UserList):
                path_1.extend(step)
            else:
                # logger.debug('get_value (1): path={} value={}'.format(path, str(step)))
                return step
        else:
            path_1.append(part)
    path_2 = UserList()
    for part in path_1:
        if repeat_variable.match(part):
            step = context[part]
            if isinstance(step, UserList):
                path_2.extend(step)
            else:
                # logger.debug('get_value (2): path={} value={}'.format(path, str(step)))
                return step
        else:
            path_2.append(part)
    for part in path_2:
        if part[0] == '[' and part[-1] == ']':
            part = part[1:-1]
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isnumeric():
            value = value[int(part)]
        elif isinstance(value, tuple) and part.isnumeric():
            value = value[int(part)]
        else:
            route = ':'.join(path_2)
            logger.error("No {} in context {}\npath={} part={} value={}".\
                           format(route, short(context), str(path_2), part, str(value)))
            raise KeyError("No {} in context {}".format(route, short(context)))
    #if path[0] not in ('content', 'verbose'):
    #    logger.debug('get_value (3): path={} value={}'.format(path, str(value)))
    return value

# Node classes for parse tree
class Node:
    """Base class for Template, Text, Expr, Partial and Block"""
    def __init__(self):
        self.children = []
        self.parent = None
        self.root = None
    def kind(self):
        return self.__class__.__name__
    def add(self, node):
        node.parent = self
        node.root = self.root
        self.children.append(node)
    def format(self, level=0):
        result = [('  '*level) + str(self)]
        for child in self.children:
            result.extend(child.format(level+1))
        return result

def argument_list(args):
    """Create dictionary {'_0':arg0, '_1':arg1, '_2':None, ...}"""
    result = {'_' + digit: None for digit in string.digits}
    for k, arg in enumerate(args):
        result['_' + str(k)] = arg
    return result

class Template(Node):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.args = []
    def __str__(self):
        return '{} {}'.format(self.kind(), self.name)
    def __call__(self, context, children=None, args=None):
        if args:
            self.args = argument_list(args)
        result = []
        for child in self.children:
            fragment = child(context, self.children, self.args)
            result.append(fragment)
        return multiple_newline.sub('\n', ''.join(result))

class Text(Node):
    def __init__(self, text):
        super().__init__()
        self.text = text
    def __str__(self):
        return "{} {}".format(self.kind(), abbrev(self.text))
    def __call__(self, context, children, args):
        return self.text

class Expr(Node):
    def __init__(self, arg, source, raw=False):
        super().__init__()
        self.arg = arg
        self.source = source
        self.raw = raw
    def __str__(self):
        return "{} {}".format(self.kind(), self.source)
    def __call__(self, context, children, args):
        arg, arg_type = self.arg, argtype(self.arg)
        if arg_type == 'number':
            return str(arg)
        elif arg_type == 'string':
            return arg
        # so it's a path-like argument
        value = get_value(arg, context, self.root)
        if isinstance(value, tuple):
            if self.raw:
                # logger.debug('Expr raw: value={}'.format(str(value)))
                return "{0} {1} {3}".format(*value)
            else:
                # logger.debug('Expr not raw: value={}'.format(str(value)))
                return "{0} <a href='{2}'>{1}</a> {3}".format(*value)
        else:
            return str(value)

class Block(Node):
    def __init__(self, name, args, source):
        super().__init__()
        self.name = name
        self.source = source
        self.args = args
    def __str__(self):
        return "{} #{} {}".format(self.kind(), self.name, self.source)
    def __call__(self, context, children, args):
        if self.name not in setting.templates:
            raise KeyError("Unknown block '{}'".format(self.name))
        template = setting.templates[self.name]
        if isfunction(template):
            return template(context, self.children, self.args, self.root)
        else:
            return template(context, self.children, self.args)

class Partial(Node):
    def __init__(self, name, args, source):
        super().__init__()
        self.name = name
        self.source = source
        self.args = args
    def __str__(self):
        return "{} >{} {}".format(self.kind(), self.name, self.source)
    def __call__(self, context, children, args):
        if self.name not in setting.templates:
            raise KeyError("Unknown partial '{}'".format(self.name))
        template = setting.templates[self.name]
        if isfunction(template):
            return template(context, self.children, self.args, self.root)
        else:
            return template(context, self.children, self.args)

# Built-in helpers
def ifdef_block(context, children, args, root):
    arg, arg_type = args[0], argtype(args[0])
    if arg_type != 'path':
        raise ValueError("ifdef: incorrect argument '{}'".format(str(arg)))
    arg = get_value(arg, context, root)
    if arg is None:
        return ''
    else:
        return ''.join(child(context, children, args) for child in children)
setting.templates['ifdef'] = ifdef_block

def compare_block(context, children, args, root, oper, name):
    arg0, arg_type0 = args[0], argtype(args[0])
    arg1, arg_type1 = args[1], argtype(args[1])
    if arg_type0 == 'path':
        value0 = get_value(arg0, context, root)
        if arg_type1 == 'string' or arg_type1 == 'number':
            value1 = arg1
        elif arg_type1 == 'path':
            value1 = get_value(arg1, context, root)
        else:
            raise ValueError("{}: incorrect 2nd argument {}".format(name, str(arg1)))
        if oper(value0, value1):
            # logger.debug('{} {}={} {}={}: condition true'.format(name, arg0, value0, arg1, value1))
            return ''.join(child(context, children, args) for child in children)
        else:
            # logger.debug('{} {}={} {}={}: condition false'.format(name, arg0, value0, arg1, value1))
            return ''
    else:
        raise ValueError("{}: incorrect 1st argument {}".format(name, str(arg0)))

def eq_block(context, children, args, root):
    return compare_block(context, children, args, root, operator.eq, 'eq')
setting.templates['eq'] = eq_block

def ne_block(context, children, args, root):
    return compare_block(context, children, args, root, operator.ne, 'ne')
setting.templates['ne'] = ne_block

def gt_block(context, children, args, root):
    return compare_block(context, children, args, root, operator.gt, 'gt')
setting.templates['gt'] = gt_block

def ge_block(context, children, args, root):
    return compare_block(context, children, args, root, operator.ge, 'ge')
setting.templates['ge'] = ge_block

def lt_block(context, children, args, root):
    return compare_block(context, children, args, root, operator.lt, 'lt')
setting.templates['lt'] = lt_block

def le_block(context, children, args, root):
    return compare_block(context, children, args, root, operator.le, 'le')
setting.templates['le'] = le_block

def if_unless_block(context, children, args, root, reverse=False):
    arg, arg_type = args[0], argtype(args[0])
    if arg_type == 'number' or arg_type == 'string':
        value = arg
    else:
        value = get_value(arg, context, root)
    condition = not bool(value) if reverse else bool(value)
    if condition:
        return ''.join(child(context, children, args) for child in children)
    else:
        return ''

def if_block(context, children, args, root):
    return if_unless_block(context, children, args, root)
setting.templates['if'] = if_block

def unless_block(context, children, args, root):
    return if_unless_block(context, children, args, root, reverse=True)
setting.templates['unless'] = unless_block

def with_block(context, children, args, root):
    arg, arg_type = args[0], argtype(args[0])
    # logger.debug('With: arg={} ({})'.format(str(arg), arg_type))
    if arg_type == 'number' or arg_type == 'string':
        raise ValueError("with: incorrect argument '{}'".format(str(arg)))
    new_context = get_value(arg, context, root)
    if not isinstance(new_context, dict):
        logger.error('with: arg={} old context={} new context={}'.\
                     format(arg, short(context), str(new_context)))
        raise ValueError('with: new context is not dictionary')
    for key in context.keys():
        if repeat_variable.match(key):
            new_context[key] = context[key]
    return ''.join(child(new_context, children, args) for child in children)
setting.templates['with'] = with_block

def repeat_block(context, children, args, root, before=None, after=None):
    arg, arg_type = args[0], argtype(args[0])
    if arg_type == 'number' or arg_type == 'string':
        raise ValueError("each: incorrect argument '{}'".format(str(arg)))
    result = []
    sequence = get_value(arg, context, root)
    if before is not None:
        sequence = sequence[:before]
    elif after is not None:
        sequence = sequence[after+1:]
    if isinstance(sequence, list):
        for key, element in enumerate(sequence):
            context['@0'] = element
            context['@first'] = key == 0
            context['@index'] = key
            result.append(''.join(child(context, children, args) for child in children))
        return ''.join(result)
    elif isinstance(sequence, dict):
        for key, element in sequence.items():
            context['@0'] = element
            context['@index'] = key
            result.append(''.join(child(context, children, args) for child in children))
        return ''.join(result)
    else:
        raise ValueError("each: component {} should be list or dict".format(arg))

def each_block(context, children, args, root):
    return repeat_block(context, children, args, root)
setting.templates['each'] = each_block

def after_block(context, children, args, root):
    arg, arg_type = args[1], argtype(args[1])
    if arg_type != 'number':
        raise ValueError("after: incorrect argument '{}'".format(str(arg)))
    return repeat_block(context, children, args, root, after=int(args[1]))
setting.templates['after']  = after_block

def before_block(context, children, args, root):
    arg, arg_type = args[1], argtype(args[1])
    if arg_type != 'number':
        raise ValueError("before: incorrect argument '{}'".format(str(arg)))
    return repeat_block(context, children, args, root, before=int(args[1]))
setting.templates['before'] = before_block

def witheach_block(context, children, args, root):
    arg, arg_type = args[0], argtype(args[0])
    if arg_type == 'number' or arg_type == 'string':
        raise ValueError("witheach: incorrect argument '{}'".format(str(arg)))
    result = []
    sequence = get_value(arg, context, root)
    if isinstance(sequence, list):
        for key, element in enumerate(sequence):
            context['@first'] = key == 0
            context['@index'] = key
            result.append(''.join(child(element, children, args) for child in children))
        return ''.join(result)
    else:
        raise ValueError("witheach: component {} should be list of dict's".format(arg))
setting.templates['witheach'] = witheach_block

# Lexical analyzer
def split_group(tag):
    s = tag[1:].strip().split()
    return s

def tokenize(source):
    s = source
    trim = False
    while s:
        if s.startswith('{{{'):
            k = s.find('}}}')
            result = s[3:k]
            s = s[k+3:]
            yield 'RAW', result.strip()
        elif s.startswith('{{'):
            k = s.find('}}')
            result = s[2:k]
            if result.endswith('~'):
                trim = True
                result = result.rstrip('~')
            s = s[k+2:]
            if result[0] == '#':
                yield ('STAG', *split_group(result))
            elif result[0] == '/':
                yield ('ETAG', *split_group(result))
            elif result[0] == '>':
                yield ('ZTAG', *split_group(result))
            elif result[0] == '!': # comment
                continue
            else:
                yield 'EXPR', result.strip()
        else:
            k = s.find('{{')
            if k > 0:
                result = s[0:k]
                s = s[k:]
            else:
                result = s
                s = ''
            if trim:
                result = result.lstrip()
                trim = False
            yield 'TEXT', result

# Parser
def convert_arg(arg):
    """Convert block or partial argument to the right type: number, string or path"""
    if arg.isnumeric():
        return int(arg)
    elif arg.startswith("'") and arg.endswith("'"):
        return arg.strip("'")
    elif arg.startswith('"') and arg.endswith('"'):
        return arg.strip('"')
    else:
        return UserList(re.split(r'[:;/]', arg))

def argtype(arg):
    """Determine type of argument: number, string, path or other(wise)"""
    if isinstance(arg, int):
        return 'number'
    elif isinstance(arg, str):
        return 'string'
    elif isinstance(arg, UserList):
        return 'path'
    else:
        return 'other'

def parse(source, name):
    """Parse template in string `source` and return instance of class TemplateNode"""
    stack, level, indent = [], 0, '  '
    current_node = Template(name)
    current_node.root = current_node
    for group in tokenize(source): # tokenize() returns groups of tokens
        if group[0] == 'STAG':
            new_node = Block(group[1], [convert_arg(token) for token in group[2:]],
                             ' '.join(group[1:]))
            current_node.add(new_node)
            stack.append(current_node)
            level += 1
            current_node = new_node
        elif group[0] == 'ETAG':
            if group[1] == current_node.name:
                current_node = stack.pop()
                level -= 1
            else:
                raise ValueError("Tag '{}' does not close current block '{}'".\
                                 format(group[1], current_node.name))
        elif group[0] == 'ZTAG':
            new_node = Partial(group[1], [convert_arg(token) for token in group[2:]],
                               ' '.join(group[1:]))
            current_node.add(new_node)
        elif group[0] == 'EXPR':
            new_node = Expr(convert_arg(group[1]), group[1])
            current_node.add(new_node)
        elif group[0] == 'RAW':
            new_node = Expr(convert_arg(group[1]), group[1], raw=True)
            current_node.add(new_node)
        elif group[0] == 'TEXT':
            new_node = Text(group[1])
            current_node.add(new_node)
        else:
            raise ValueError("Unrecognized token '{}'".format(group[0]))
    if stack:
        raise ValueError("Missing closing tag(s): current block is '{}'". \
                         format(current_node.name))
    return current_node