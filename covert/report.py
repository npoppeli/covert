# -*- coding: utf-8 -*-
"""
covert.report
-----
Objects and functions related to reporting, logging etcetera.
"""

import datetime, json, logging
from .common import ComplexEncoder

# logging levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
logger = logging.getLogger('waitress')
logger.setLevel(logging.DEBUG)

# logger = logging.getLogger('covert')
# logger.setLevel(logging.DEBUG)
# console = logging.StreamHandler()
# console.setLevel(logging.DEBUG)
# formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(message)s')
# console.setFormatter(formatter)
# logger.addHandler(console)

def print_doc(doc):
    return json.dumps(doc, sort_keys=True, indent=2, separators=(',', ': '), cls=ComplexEncoder)

# print node in similar fashion to print_doc, but more compact
def print_node(node, level=0):
    def terminal(node):
        return 'children' not in node
    lines = []
    car = ', '.join(["'{0}': '{1}'".format(key, str(node[key]))
                     for key in sorted(node.keys()) if key != 'children'])
    if terminal(node):
        lines.append('{ '+car+' }')
    elif len(node['children']) == 0:
        cdr = ", 'children': []"
        lines.append('{ '+car+cdr+' }')
    elif len(node['children']) == 1 and terminal(node['children'][0]):
        lines.append('{ '+car+',')
        cdr = "    'children': [ "+print_node(node['children'][0], 0)+" ] }"
        lines.append(cdr)
    else:
        lines.append('{ '+car+',')
        lines.append("  'children': [")
        cdr = [print_node(el, level+1)+',' for el in node['children']]
        lines.extend(cdr)
        lines.append("] }")
    indent = 2*level*' '
    return '\n'.join([indent+line for line in lines])

