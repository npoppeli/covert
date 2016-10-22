# -*- coding: utf-8 -*-
"""Objects and functions related to templates.
"""

from os import walk
from os.path import join, splitext, relpath
from chameleon import PageTemplateFile
from . import setting

def read_templates():
    """read templates from layout directory"""
    template_types = ['.xml', '.pt']
    print('Scanning for templates in {0}'.format(setting.layout))
    for (dirpath, __, filenames) in walk(setting.layout):
        prefix = relpath(dirpath, setting.layout)
        for filename in filenames:
            name, extension = splitext(filename)
            if extension in template_types:
                if prefix == '.':
                    template_name = name
                else:
                    template_name = prefix.replace('/', '_')+'_'+name
                file_path = join(dirpath, filename)
                try:
                    setting.templates[template_name] = PageTemplateFile(file_path)
                except Exception as e:
                    print("Error in template '{0}' in file {1}".format(template_name, file_path))
                    print(str(e))
