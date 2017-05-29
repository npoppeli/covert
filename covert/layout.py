# -*- coding: utf-8 -*-
"""Objects and functions related to layout.

The layout of HTML pages, and HTML and XML fragments is specified by templates.
In the current implementation only Chameleon templates are supported.
"""

import sys
from os import walk
from os.path import join, splitext, relpath
from . import setting
from .common import logger
from .controller import exception_report

# By default, there is one template factory: chameleon.PageTemplateFile. This is associated
# with the file extension '.pt'. Other template factories can be defined, provided they
# implement the following interface:
#   - filename -> template: template = template_factory(filename)
#   - context  -> string: template.render(this=context) returns HTML page for context 'this' (dict)
# Template factories are stored in a dictionary template_factory, with the extension as key.

# TODO: Tonnikala and Mako are added here temporarily, but should move to application level
template_factory = {}

def add_template_type(extension, factory):
    """Add template factory for given suffix.

    :param extension: file extension (.foo)
    :param factory:   template factory (callable object)

    Returns:
        None
    """
    if extension in template_factory:
        logger.debug('Cannot redefine template type %s', extension)
    else:
        logger.debug('Define new template type %s', extension)
        template_factory[extension] = factory

try:
    from chameleon import PageTemplateFile
    add_template_type('.pt', PageTemplateFile)
except ImportError as e:
    logger.critical('Chameleon template engine not available (%s)', e)
    sys.exit(1)

try:
    from tonnikala import FileLoader
    tkLoader = FileLoader()
    class TkTemplateFile:
        def __init__(self, path):
            super().__init__()
            if not tkLoader.paths:
                tkLoader.add_path(setting.layout)
            self.template = tkLoader.load(relpath(path, setting.layout))
        def render(self, **vars):
            return self.template.render_to_buffer(vars, '__main__').join()
    add_template_type('.tk', TkTemplateFile)
except ImportError as e:
    logger.critical('Tonnikala template engine not available (%s)', e)
    sys.exit(1)

try:
    from mako.template import Template
    def makoTemplateFile(path):
        return Template(filename=path)
    add_template_type('.mko', makoTemplateFile)
except ImportError as e:
    logger.critical('Mako template engine not available (%s)', e)
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
            if extension in template_types:
                if prefix == '.':
                    template_name = name
                else:
                    template_name = prefix.replace('/', '_')+'_'+name
                file_path = join(dirpath, filename)
                try:
                    setting.templates[template_name] = template_factory[extension](file_path)
                    logger.debug("Template {} is in file {}".format(template_name, relpath(file_path, setting.layout)))
                except Exception as e:
                    logger.error("Error in template '{0}' in file {1}".format(template_name, file_path))
                    logger.error(exception_report(e, ashtml=False))
