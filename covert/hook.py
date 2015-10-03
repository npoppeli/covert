# -*- coding: utf-8 -*-
"""
covert.hook
-----
Objects and functions related to hooks.

Kernel map:
  hooks = {
    'page.top':     [page_top_1, page_top_2],
    'page.content': [page_content_1, page_content_2],
    'page.bottom':  [page_bottom_1, page_bottom_2]
  }
where each element in a hook list is a function of one parameter, namely
a node in the render tree.
Hooks are usually registered by modules. TODO: switch to event model of Bass.

A module is a Python file in the special 'modules' directory.
"""

from .template import node

def hook_page_attachments(page_node):
   header  = node('region', 'header',  content='')
   sidebar = node('region', 'sidebar', content='SIDEBAR')
   footer  = node('region', 'footer',  content='&copy; 2015')
   page_node['children'].insert(0, header)
   page_node['children'].append(sidebar)
   page_node['children'].append(footer)

def hook_page_top(html_node):
    pass

def hook_page_bottom(html_node):
    pass
