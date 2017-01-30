# -*- coding: utf-8 -*-
"""Objects and functions related to layout.

The layout of HTML pages, and HTML and XML fragments is specified by templates.
In the current implementation only Chameleon templates are supported.
"""

import sys
from os import walk
from os.path import join, splitext, relpath
from . import setting
from .common import logger, read_file

# By default, there is one template factory: chameleon.PageTemplateFile. This is associated
# with the file extension '.pt' (suffix 'pt'). Other template
# factories can be defined, provided they implement the following interface:
#   - filename -> template: template = template_factory(filename)
#   - node     -> string: template.render(this=node) returns HTML page for node 'this'
#                 (condition: node.skin should be equal to filename without extension)
# Template factories are stored in a dictionary template_factory, with the suffix as key.

# TODO: Tonnikala is added here temporarily, but should move to application level
template_factory = {}

def add_template_type(suffix, factory):
    """Add template factory for given suffix.

    :param suffix: file extension minus the period
    :param factory: template factory (callable object)

    Returns:
        None
    """
    if suffix in template_factory:
        logger.debug('Cannot redefine template type %s', suffix)
    else:
        logger.debug('Define new template type %s', suffix)
        template_factory[suffix] = factory

try:
    from chameleon import PageTemplateFile
    add_template_type('pt', PageTemplateFile)
except ImportError:
    logger.critical('Chameleon template engine not available')
    sys.exit(1)

try:
    from tonnikala import Loader
    class TkTemplateFile(Loader):
        def __init__(self, path):
            super().__init__()
            self.template = self.load_string(read_file(path))
            self.path = path
        def render(self, **vars):
            return self.template.render_to_buffer(vars, '__main__').join()
    add_template_type('tk', TkTemplateFile)
except ImportError:
    logger.critical('Tonnikala template engine not available')
    sys.exit(1)

def read_templates():
    """Read templates from layout directory.

    Read templates, compile them and store compiled templates in global variable 'templates'.

    Returns:
        None
    """
    template_types = list(template_factory.keys())
    logger.debug('Scanning for templates in {0}'.format(setting.layout))
    logger.debug('Template types: {0}'.format(' '.join(template_types)))
    for (dirpath, __, filenames) in walk(setting.layout):
        prefix = relpath(dirpath, setting.layout)
        for filename in filenames:
            name, extension = splitext(filename)
            suffix = extension[1:]
            if suffix in template_types:
                if prefix == '.':
                    template_name = name
                else:
                    template_name = prefix.replace('/', '_')+'_'+name
                file_path = join(dirpath, filename)
                try:
                    setting.templates[template_name] = template_factory[suffix](file_path)
                except Exception as e:
                    logger.error("Error in template '{0}' in file {1}".format(template_name, file_path))
                    logger.error(str(e))
