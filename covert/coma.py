# -*- coding: utf-8 -*-
"""Objects and functions related to templates.

The layout of HTML pages, and HTML and XML fragments is specified by templates.
COvert's Mustache Analog is a template engine that on the surface resembles Mustache
and Handlebars but is actually quite different.
"""

import re
from . import setting

multiple_newline = re.compile(r'\n *\n')
list_index = re.compile(r'\[\d+\]')

def split_tag(tag):
    s = tag[3:-2].strip().split()
    return s

def abbrev(s):
    return s.strip().replace('\n', ' ')[0:50] + '...'

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
        self.children = []
    def add(self, node):
        """add child node"""
        self.children.append(node)

def get_value(path, context):
    parts = path.split('.')
    value = context
    for part in parts:
        if part in value:
            value = value[part]
        elif isinstance(value, list) and list_index.match(part):
            value = value[int(part[1:-1])]
        else:
            raise KeyError("No '{}' in context {} (part={})".\
                           format(path, str(context), part))
    return value

def get_argument(path, context):
    if '_args' in context:
        args = context['_args']
        if path[1:].isnumeric() and int(path[1:]) <= len(args):
            return args[int(path[1:])-1]
        else:
            raise ValueError("Incorrect argument reference {}; args={}".\
                             format(path, args))
    else:
        raise KeyError("No '_args' in context {}".format(path, str(context)))

class Template(Node):
    def __init__(self, name):
        super().__init__()
        self.kind = 'Template'
        self.name = name
    def __str__(self):
        return '{} {} [{}]'.format(self.kind, self.name, len(self.children))
    def __call__(self, context, children=None, *args):
        result = []
        context['_args'] = args
        for child in self.children:
            fragment = child(context, self.children)
            result.append(fragment)
        return multiple_newline.sub('\n', ''.join(result))

class Text(Node):
    def __init__(self, text):
        super().__init__()
        self.kind = 'Text'
        self.text = text
    def __str__(self):
        return "{} '{}'".format(self.kind, abbrev(self.text))
    def __call__(self, context, children, *args):
        return self.text

class Expr(Node):
    def __init__(self, path):
        super().__init__()
        self.kind = 'Expr'
        self.path = path
    def __str__(self):
        return "{} '{}'".format(self.kind, self.path)
    def __call__(self, context, children, *args):
        if self.path.startswith('@'):
            return get_argument(self.path, context)
        else:
            return get_value(self.path, context)

class Partial(Node):
    def __init__(self, name, *args):
        super().__init__()
        self.kind = 'Partial'
        self.name = name
        self.args = args
    def __str__(self):
        return "{} '{}'".format(self.kind, self.name)
    def __call__(self, context, children, *args):
        if self.name in setting.templates:
            func = setting.templates[self.name]
            print("Partial {} arguments={}".format(self.name, str(self.args)))
            return func(context, [], *self.args)
        else:
            raise KeyError("No definition for '{}'".format(self.name))

class Block(Node):
    def __init__(self, name, *args):
        """create Block node"""
        super().__init__()
        self.kind = 'Block'
        self.name = name
        self.args = args
    def __str__(self):
        return "{} '{}'".format(self.kind, self.name)
    def __call__(self, context, children, *args):
        if self.name in setting.templates:
            func = setting.templates[self.name]
            print("Block {} arguments={}".format(self.name, str(self.args)))
            return func(context, self.children, *self.args)
        else:
            raise KeyError("No definition for '{}'".format(self.name))

def if_block(context, children, *args):
    value = get_value(args[0], context)
    if bool(value):
        return ''.join(child(context, children) for child in children)
    else:
        return ''

def unless_block(context, children, *args):
    value = get_value(args[0], context)
    if bool(value):
        return ''
    else:
        return ''.join(child(context, children) for child in children)

def with_block(context, children, *args):
    path = args[0]
    if path.startswith('@'):
        new_context = get_value(get_argument(path, context), context)
    else:
        new_context = get_value(path, context)
    # new context 'inherits' _args from parent context
    new_context['_args'] = context.get('_args', [])
    return ''.join(child(new_context, children) for child in children)

def repeat_block(context, children, *args):
    path = args[0]
    new_context = get_value(path, context)
    if isinstance(new_context, list):
        result = []
        for elt in new_context:
            result.append(''.join(child(new_context, children) for child in children))
        return ''.join(result)
    else:
        raise ValueError("Component {} in context '{}' is not a list". \
                        format(path, str(context)))

# Parser (also simple)
def parse(source, name):
    stack = []
    current_node = Template(name)
    for token in tokenize(source):
        if token[0] == 'STAG':
            new_node = Block(token[1], *token[2:])
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
            new_node = Partial(token[1], *token[2:])
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
