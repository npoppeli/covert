# -*- coding: utf-8 -*-
"""Objects and functions related to templates.

The layout of HTML pages, and HTML and XML fragments is specified by templates.
COvert's Mustache Analog (COMA) is a template engine that superficially resembles
Mustache and Handlebars but under the hood is quite different.

Conventions:
* loop handlers (e.g. each) put the loop variables in @1, @2, ... in the context
* templates that are used as macros have implicit arguments #1, #2, ...,
  which must be evaluated before evaluating ('calling') the template
"""

import re
from inspect import isfunction
from . import setting
from . import common as c
from .common import logger

multiple_newline = re.compile(r'\n *\n')
list_index = re.compile(r'\[\d+\]')
bracketed = re.compile(r'\[.+?\]')
word = re.compile(r'\w+')

def split_tag(tag):
    s = tag[3:-2].strip().split()
    return s

def abbrev(s):
    s0 = s.strip().replace('\n', ' ')
    return s0[0:50] + '...' if len(s0)>50 else s0

# Lexical analyzer (simple)
def tokenize(source):
    s = source
    while s:
        if s.startswith('{{'):
            k = s.find('}}')
            result = s[0:k+2]
            s = s[k+2:]
            if result[2] == '#':
                yield ('STAG', *split_tag(result))
            elif result[2] == '/':
                yield ('ETAG', *split_tag(result))
            elif result[2] == '>':
                yield ('ZTAG', *split_tag(result))
            elif result[2] == '!':
                continue
            else:
                yield 'EXPR', result[2:-2].strip()
        else:
            k = s.find('{{')
            if k > 0:
                result = s[0:k]
                s = s[k:]
            else:
                result = s
                s = ''
            yield ('TEXT', result)

# Node classes for parse tree
class Node:
    """Base class for Template, Text, Expr, Partial and Block"""
    def __init__(self):
        self.kind = 'Node'
        self.name = 'Node'
        self.children = []
    def add(self, node):
        """add child node"""
        self.children.append(node)
    def format(self, level=0):
        result = [('  '*level) + str(self)]
        for child in self.children:
            result.extend(child.format(level+1))
        return result

def short(context):
    return "{}\nargs={}".format(', '.join(context.keys()), str(context.get('_args', '')))

def split_path(path, sep):
    """consume bracketed or word-like parts until we meet something in sep"""
    result, original = [], path
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
            raise ValueError("Incorrect path '{}'".format(original))
        if path: # there is text left, so check the separator
            if path[0] in sep:
                path = path[1:]
            else:
                raise ValueError("Incorrect separator '{}' in path '{}'".format(path[0], original))
    return result

def get_value(path, context, default=None):
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

class Template(Node):
    def __init__(self, name):
        super().__init__()
        self.kind = 'Template'
        self.name = name
    def __str__(self):
        return '{} {} [{}]'.format(self.kind, self.name, len(self.children))
    def __call__(self, context, children=None):
        # logger.debug(str(self))
        result = []
        if '_args' not in context:
            context['_args'] = {}
        for child in self.children:
            fragment = child(context, self.children)
            result.append(fragment)
        return multiple_newline.sub('\n', ''.join(result))
    def expand(self, args):
        expanded = Template(self.name)
        for child in self.children:
            expanded.children.append(child.expand(args))
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
    def expand(self, args):
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
        # logger.debug(str(self))
        return get_value(self.path, context, default=self.path)
    def expand(self, args):
        if self.path.startswith('@'):
            exp_path = args[int(self.path[1:]) - 1]
        else:
            exp_path = self.path
        return Expr(exp_path)

def evaluate(args, context):
    return [context['_'] if arg == '_' else arg for arg in args]

class Block(Node):
    def __init__(self, name, args):
        """create Block node"""
        super().__init__()
        self.kind = 'Block'
        self.name = name
        self.args = args
    def __str__(self):
        return "{} '{}' {}".format(self.kind, self.name, ' '.join(self.args))
    def __call__(self, context, children, *args):
        # logger.debug(str(self))
        if self.name not in setting.templates:
            raise KeyError("No definition for '{}'".format(self.name))
        template = setting.templates[self.name]
        if isfunction(template):
            # logger.debug('Block: {} function {}'.format(self.name, ' '.join(self.args)))
            return template(context, self.children, *self.args)
        else:
            # expand @1, @2, ... which yields new Template instance
            args = evaluate(self.args, context)
            # logger.debug('  Block.call: evaluated args={}'.format(str(args)))
            expanded_template = template.expand(args)
            fmt = expanded_template.format()
            # logger.debug('  Block.call: {} expanded template\n{}'.format(self.name, '\n'.join(fmt)))
            return expanded_template(context, self.children)
    def expand(self, args):
        # logger.debug('  Block.expand: args={}'.format(str(args)))
        expanded = Block(self.name, [])
        for arg in self.args:
            expanded.args.append(args[int(arg[1:]) - 1] if arg.startswith('@') else arg)
        for child in self.children:
            expanded.children.append(child.expand(args))
        return expanded

class Partial(Node):
    def __init__(self, name, args):
        super().__init__()
        self.kind = 'Partial'
        self.name = name
        self.args = args
    def __str__(self):
        return "{} '{}' {}".format(self.kind, self.name, ' '.join(self.args))
    def __call__(self, context, children, *args):
        # logger.debug(str(self))
        if self.name not in setting.templates:
            raise KeyError("No definition for '{}'".format(self.name))
        template = setting.templates[self.name]
        if isfunction(template):
            # logger.debug('Partial: {} function {}'.format(self.name, ' '.join(self.args)))
            return template(context, [], *self.args)
        else:
            # expand @1, @2, ... which yields new Template instance
            args = evaluate(self.args, context)
            # logger.debug('  Partial.call: evaluated args={}'.format(str(args)))
            expanded_template = template.expand(args)
            fmt = expanded_template.format()
            # logger.debug('  Partial.call: {} expanded template\n{}'.format(self.name, '\n'.join(fmt)))
            return expanded_template(context, self.children)
    def expand(self, args):
        # logger.debug('  Partial.expand: args={}'.format(str(args)))
        expanded = Partial(self.name, [])
        for arg in self.args:
            for arg in self.args:
                expanded.args.append(args[int(arg[1:]) - 1] if arg.startswith('@') else arg)
        for child in self.children:
            expanded.children.append(child.expand(*args))
        return expanded

def if_block(context, children, *args):
    # logger.debug('if: arg0={}'.format(args[0]))
    value = get_value(args[0], context)
    if bool(value):
        return ''.join(child(context, children) for child in children)
    else:
        return ''

def unless_block(context, children, *args):
    # logger.debug('unless: arg0={}'.format(args[0]))
    value = get_value(args[0], context)
    if bool(value):
        return ''
    else:
        return ''.join(child(context, children) for child in children)

def with_block(context, children, *args):
    # logger.debug('with: arg0={}'.format(args[0]))
    new_context = get_value(args[0], context)
    new_context['_'] = context.get('_', None)
    return ''.join(child(new_context, children) for child in children)

def each_block(context, children, *args):
    # logger.debug('each: arg0={}'.format(args[0]))
    path = args[0]
    sequence = get_value(path, context)
    if isinstance(sequence, list):
        result = []
        if isinstance(sequence[0], dict):
            # logger.debug("each_block: path={} dict list".format(path))
            for element in sequence:
                result.append(''.join(child(element, children) for child in children))
        else:
            # logger.debug("each_block: path={} scalar list".format(path))
            for element in sequence:
                context['@1'] = element
                result.append(''.join(child(context, children) for child in children))

        return ''.join(result)
    else:
        raise ValueError("Component '{}' in context {} is not a list".format(path, short(context)))

# Parser (also simple)
def parse(source, name):
    """Parse template in string `source` and return instance of class TemplateNode"""
    stack = []
    current_node = Template(name)
    for token in tokenize(source):
        if token[0] == 'STAG':
            new_node = Block(token[1], list(token[2:]))
            current_node.add(new_node)
            stack.append(current_node)
            current_node = new_node
        elif token[0] == 'ETAG':
            if token[1] == current_node.name:
                current_node = stack.pop()
            else:
                raise ValueError("Tag '{}' does not close current block '{}'".\
                                 format(token[1], current_node.name))
        elif token[0] == 'ZTAG':
            new_node = Partial(token[1], list(token[2:]))
            current_node.add(new_node)
        elif token[0] == 'EXPR':
            new_node = Expr(token[1])
            current_node.add(new_node)
        elif token[0] == 'TEXT':
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
