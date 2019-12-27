# -*- coding: utf-8 -*-
"""Objects and functions related to templates.

The layout of HTML pages, and HTML and XML fragments is specified by templates.
COvert's Mustache Analog (COMA) is a template engine that superficially resembles
Mustache and Handlebars but under the hood is quite different.

Conventions:
* loop handlers (e.g. each) put the loop variables in @0, @1, ... in the context
* templates that are used as macros have implicit arguments _0, _1, ...,
  which get their values from the context
"""

import re, string
from inspect import isfunction
from . import setting
from . import common as c
from .common import logger

multiple_newline = re.compile(r'\n *\n')
list_index = re.compile(r'\[\d+\]')
bracketed = re.compile(r'\[.+?\]')
word = re.compile(r'\w+')

# various auxiliary functions
def split_tag(tag):
    s = tag[1:].strip().split()
    return s

def abbrev(s):
    s0 = s.strip().replace('\n', ' ')
    return s0[0:50] + '...' if len(s0)>50 else s0

def short(context):
    return "{}".format(', '.join(context.keys()))

def split_path(path, sep):
    """consume bracketed or word-like parts until we meet something in sep"""
    result, original = [], path
    # logger.debug('split_path: path={}'.format(str(path)))
    while path:
        mo1 = bracketed.match(path)
        mo2 = word.match(path)
        if mo1:
            path = path.replace(mo1.group(0), '', 1)
            result.append(mo1.group(0)[1:-1])
        elif mo2:
            path = path.replace(mo2.group(0), '', 1)
            result.append(mo2.group(0))
        else:
            raise ValueError(c._("Incorrect path '{}'").format(original))
        if path: # there is text left, so check the separator
            if path[0] in sep:
                path = path[1:]
            else:
                raise ValueError(c._("Incorrect separator '{}' in path '{}'").format(path[0], original))
    return result

def get_value(path, context, default=None):
    if path == '':
        raise ValueError("Cannot lookup value with empty path")
    if setting.debug>1: logger.debug('get_value: path={}'.format(str(path)))
    parts = split_path(path, ':;/.')
    value = context
    for part in parts:
        if part in value:
            value = value[part]
        elif isinstance(value, list) and part.isnumeric():
            value = value[int(part)]
        elif default:
            value = default
        else:
            raise KeyError("No '{}' in context {} (part={})".format(path, short(context), part))
    return value

special_variable = re.compile(r'^@(?:\d+|index|first)$')
def evaluate(args, context):
    if any(arg is None for arg in args):
        logger.debug("evaluate: args={}".format(str(args)))
    return [context[arg] if special_variable.match(arg) else arg for arg in args]

# Lexical analyzer (simple)
def tokenize(source):
    s = source
    trim = False
    while s:
        if s.startswith('{{'):
            k = s.find('}}')
            result = s[2:k]
            if result.endswith('~'):
                trim = True
                result = result.rstrip('~')
            s = s[k+2:]
            if result[0] == '#':
                yield ('STAG', *split_tag(result))
            elif result[0] == '/':
                yield ('ETAG', *split_tag(result))
            elif result[0] == '>':
                yield ('ZTAG', *split_tag(result))
            elif result[0] == '!':
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

# Node classes for parse tree
class Node:
    """Base class for Template, Text, Expr, Partial and Block"""
    def __init__(self):
        self.kind = 'Node'
        self.name = 'Node'
        self.children = []
        self.parent = None
        self.root = None
    def add(self, node):
        """add child node"""
        node.parent = self
        node.root = self.root
        self.children.append(node)
    def format(self, level=0):
        result = [('  '*level) + str(self)]
        for child in self.children:
            result.extend(child.format(level+1))
        return result

class Template(Node):
    def __init__(self, name):
        super().__init__()
        self.kind = 'Template'
        self.name = name
    def __str__(self):
        return '{} {}'.format(self.kind, self.name)
    def __call__(self, context, children=None):
        """TODO: restore args, assign this to self.args, and use these values
        as substitutes for _[0-9] in all nodes of this tree"""
        # logger.debug(str(self))
        result = []
        for child in self.children:
            fragment = child(context, self.children)
            result.append(fragment)
        return multiple_newline.sub('\n', ''.join(result))
    def expand(self, params):
        expanded = Template(self.name)
        for child in self.children:
            expanded.children.append(child.expand(params))
        return expanded

class Text(Node):
    def __init__(self, text):
        super().__init__()
        self.kind = 'Text'
        self.name = 'Text'
        self.text = text
    def __str__(self):
        return "{} {}".format(self.kind, abbrev(self.text))
    def __call__(self, context, children):
        # logger.debug(str(self))
        return self.text
    def expand(self, params):
        return self

class Expr(Node):
    def __init__(self, path):
        super().__init__()
        self.kind = 'Expr'
        self.name = 'Expr'
        self.path = path
    def __str__(self):
        return "{} {}".format(self.kind, self.path)
    def __call__(self, context, children):
        if setting.debug>1: logger.debug(str(self))
        if special_variable.match(self.path):
            value = context[self.path]
        else:
            value = get_value(self.path, context, default=self.path)
        if isinstance(value, tuple):
            if setting.debug > 1:
                logger.debug("Expr.call: {}".format(str(value)))
            return "{0} <a href='{2}'>{1}</a> {3}".format(*value)
        else:
            return str(value)

    def expand(self, params):
        if self.path.startswith('_'):
            if setting.debug > 1: logger.debug("expr_expand: path={} params={}".\
                                               format(self.path, str(params)))
            exp_path = params[self.path]
        else:
            exp_path = self.path
        return Expr(exp_path)

def make_params(args):
    # result = {'_'+k:None for k in string.digits}
    result = {'_'+k:'' for k in string.digits}
    for k, value in enumerate(args):
        result['_'+str(k)] = args[k]
    return result

class Block(Node):
    def __init__(self, name, args):
        """create Block node"""
        super().__init__()
        self.kind = 'Block'
        self.name = name
        self.args = args
    def __str__(self):
        l = [str(arg) for arg in self.args]
        return "{} #{} {}".format(self.kind, self.name, ' '.join(l))
    def __call__(self, context, children, *args):
        if setting.debug>1: logger.debug(str(self))
        if self.name not in setting.templates:
            raise KeyError("No definition for '{}'".format(self.name))
        template = setting.templates[self.name]
        args = evaluate(self.args, context)
        if isfunction(template):
            if setting.debug>1: logger.debug('  Block: call function, args='+str(args))
            return template(context, self.children, *args)
        else:
            params = make_params(args)
            expanded_template = template.expand(params)
            return expanded_template(context, self.children)
    def expand(self, params):
        # # logger.debug('  Block.expand: args={}'.format(str(args)))
        expanded = Block(self.name, [])
        for arg in self.args:
            expanded.args.append(params[arg] if arg.startswith('_') else arg)
        for child in self.children:
            expanded.children.append(child.expand(params))
        return expanded

class Partial(Node):
    def __init__(self, name, args):
        super().__init__()
        self.kind = 'Partial'
        self.name = name
        self.args = args
    def __str__(self):
        return "{} >{} {}".format(self.kind, self.name, ' '.join(self.args))
    def __call__(self, context, children, *args):
        if setting.debug>1: logger.debug(str(self))
        if self.name not in setting.templates:
            raise KeyError("No definition for '{}'".format(self.name))
        template = setting.templates[self.name]
        args = evaluate(self.args, context)
        if isfunction(template):
            if setting.debug>1: logger.debug('  Partial: call function, args='+str(args))
            return template(context, [], *args)
        else:
            params = make_params(args)
            expanded_template = template.expand(params)
            return expanded_template(context, self.children)
    def expand(self, params):
        # logger.debug('  Partial.expand: args={}'.format(str(args)))
        expanded = Partial(self.name, [])
        for arg in self.args:
            expanded.args.append(params[arg] if arg.startswith('_') else arg)
        for child in self.children:
            expanded.children.append(child.expand(params))
        return expanded

def if_block(context, children, *args):
    arg = args[0]
    if arg == '':
        return ''
    elif isinstance(arg, bool):
        value = arg
    else:
        value = get_value(arg, context)
    if setting.debug>1: logger.debug('if: arg={}'.format(arg))
    if bool(value):
        return ''.join(child(context, children) for child in children)
    else:
        return ''

def unless_block(context, children, *args):
    arg = args[0]
    if arg == '':
        return ''
    elif isinstance(arg, bool):
        value = arg
    else:
        value = get_value(arg, context)
    if setting.debug>1: logger.debug('unless: arg={}'.format(arg))
    if bool(value):
        return ''
    else:
        return ''.join(child(context, children) for child in children)

def with_block(context, children, *args):
    arg = args[0]
    if setting.debug>1: logger.debug('with: arg={}'.format(arg))
    new_context = get_value(arg, context)
    for key in context.keys():
        if special_variable.match(key):
            new_context[key] = context[key]
    return ''.join(child(new_context, children) for child in children)

def each_block(context, children, *args):
    arg = args[0]
    if isinstance(arg, list):
        sequence = arg
    else:
        sequence = get_value(arg, context)
    if isinstance(sequence, list):
        result = []
        if isinstance(sequence[0], dict):
            for element in sequence:
                if setting.debug>1: logger.debug('each (d): element={}'.format(element))
                result.append(''.join(child(element, children) for child in children))
        else:
            for k, element in enumerate(sequence):
                if setting.debug>1: logger.debug('each (s): k, element={}, {}'.format(k, element))
                context['@0'] = element
                context['@first'] = k == 0
                context['@index'] = k
                result.append(''.join(child(context, children) for child in children))
        return ''.join(result)
    else:
        raise ValueError(c._("Component '{}' in context {} is not a list").format(arg, short(context)))

# Parser (also simple)
def parse(source, name):
    """Parse template in string `source` and return instance of class TemplateNode"""
    stack = []
    # print('\nParse template '+name)
    current_node = Template(name)
    current_node.root = current_node
    for token in tokenize(source):
        if token[0] == 'STAG':
            # print(' '.join(token))
            new_node = Block(token[1], list(token[2:]))
            current_node.add(new_node)
            stack.append(current_node)
            current_node = new_node
        elif token[0] == 'ETAG':
            # print(' '.join(token))
            if token[1] == current_node.name:
                current_node = stack.pop()
            else:
                raise ValueError(c_("Tag '{}' does not close current block '{}'").\
                                 format(token[1], current_node.name))
        elif token[0] == 'ZTAG':
            # print(' '.join(token))
            new_node = Partial(token[1], list(token[2:]))
            current_node.add(new_node)
        elif token[0] == 'EXPR':
            # print(' '.join(token))
            new_node = Expr(token[1])
            current_node.add(new_node)
        elif token[0] == 'TEXT':
            # print("{} {}".format(token[0], abbrev(token[1])))
            new_node = Text(token[1])
            current_node.add(new_node)
        else:
            raise ValueError("Unrecognized token '{}'".format(token[0]))
    if stack:
        raise ValueError("Missing closing tag(s): current block is '{}'". \
                         format(current_node.name))
    return current_node

# blocks that are pre-defined as functions
setting.templates['if']     = if_block
setting.templates['unless'] = unless_block
setting.templates['each']   = each_block
setting.templates['with']   = with_block
