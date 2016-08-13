# -*- coding: utf-8 -*-
"""
covert.template
-----
Objects and functions related to templates.
"""

from os import walk
from os.path import join, splitext, relpath
from chameleon import PageTemplateFile
from .report import logger
from . import setting

def read_templates():
    """read templates from layout directory"""
    template_types = ['.xml', '.pt']
    print('Scanning for templates in {0}'.format(setting.layout))
    for (dirpath, _, filenames) in walk(setting.layout):
        prefix = relpath(dirpath, setting.layout)
        for filename in filenames:
            name, extension = splitext(filename)
            if extension in template_types:
                if prefix == '.':
                    template_name = name
                else:
                    template_name = prefix.replace('/', '_')+'_'+name
                filepath = join(dirpath, filename)
                try:
                    # print("Template '{0}' in file {1}".format(template_name, filepath))
                    setting.templates[template_name] = PageTemplateFile(filepath)
                except Exception as e:
                    print("Error in template '{0}' in file {1}".format(template_name, filepath))
                    print(str(e))
