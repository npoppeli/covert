# -*- coding: utf-8 -*-
"""
covert.template
-----
Objects and functions related to templates.
"""

from os import chdir
from glob import glob
from chameleon import PageTemplate
from .atom import atom_map
from .report import logger
from .common import Error

# templates and display functions for fields are in the same dictionary:
# 'show-datetime-html'  => display function for datetime type
# 'input-datetime-html' => template for datetime input in form
template_map = {}
template_dir = ''
for key in atom_map:
    template_map['show-'+key+'-html'] = atom_map[key].display

def register_templates(path):
    template_dir = path
    chdir(template_dir)
    for filename in glob('*.xml'):
        name = filename.replace('.xml', '')
        with open(filename) as f:
            text = ''.join(f.readlines()).rstrip()
            try:
                template_map[name] = PageTemplate(text)
            except Exception as e:
                logger.debug('error in template for {0} in file {1}'.format(name, filename))
                logger.debug(str(e))

# Nodes in the rendering tree have two kinds of attributes:
# - metadata: _family, _genus
# - data: label, value, children
# Example:  {'_family': 'region', 'children': [child1, child2, child3]}
def node(family, genus, **kwarg):
    result = {'_family':family, '_genus':genus}
    result.update(kwarg)
    return result

def render(node, format='html'):
    if 'children' in node:
        node['content'] = separator.join([render(e) for e in node['children']])
    name = '-'.join((node['_family'], node['_genus'] or 'none', format))
    if name in template_map:
        return template_map[name](**node)
    raise Error('no template defined for '+name)
