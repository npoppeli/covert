# -*- coding: utf-8 -*-
"""Objects and functions related to layout.

The layout of HTML pages, and HTML and XML fragments is specified by templates.
In the current implementation only Chameleon templates are supported.
"""

from os import walk
from os.path import join, splitext, relpath
from chameleon import PageTemplateFile
from . import setting
from .common import logger

def read_templates():
    """Read templates from layout directory.

    Read templates, compile them and store compiled templates in global variable 'templates'.

    Returns:
        None
    """
    template_types = ['.xml', '.pt']
    logger.debug('Scanning for templates in {0}'.format(setting.layout))
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
                    logger.error("Error in template '{0}' in file {1}".format(template_name, file_path))
                    logger.error(str(e))
