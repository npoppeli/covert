# -*- coding: utf-8 -*-
"""Objects and functions related to layout.

The layout of HTML pages, and HTML and XML fragments is specified by templates.
In the current implementation Chameleon templates are supported out-of-the-box.
Other template engines can be added by the application.
"""

import sys
from datetime import datetime
from os import walk
from os.path import join, splitext, relpath, getmtime
from . import setting
from . import common as c
from .common import logger, exception_report

# By default, there is two template factories: ComaTemplateFile (built-in) and
# chameleon.PageTemplateFile.
# Other template factories can be defined, provided they implement the following interface:
#   - filename -> template: template = template_factory(filename)
#   - context  -> string: template.render(tree) returns HTML page for context tree 'tree' (dict)
# Template factories are stored in a dictionary 'template_factory', with the extension as key.

template_loader = {}

def add_template_type(loader):
    """Add template loader.

    Arguments:
      loader (class): template loader

    Returns:
        None
    """
    if loader.extension in template_loader:
        logger.debug(c._('Cannot redefine template type %s'), loader.extension)
    else:
        template_loader[loader.extension] = loader
        if setting.debug >= 2:
            logger.debug(c._('Define new template type %s'), loader.extension)

class TemplateLoader:
    """Instances of this class define a template loader.

    Attributes:
        * extension: file extension of templates
        * factory  : callable object that generates a template, which must be a callable too.
    """
    def __init__(self, extension, factory):
        self.extension = extension
        self.factory   = factory
        self.template  = {}
        self.timestamp = datetime.now()
        self.reload    = False
    def find(self):
        for (dirpath, __, filenames) in walk(setting.layout):
            prefix = relpath(dirpath, setting.layout)
            for filename in filenames:
                name, extension = splitext(filename)
                if extension == self.extension:
                    if prefix == '.':
                        template_name = name
                    else:
                        template_name = prefix.replace('/', '_') + '_' + name
                    filepath = join(dirpath, filename)
                    self.template[template_name] = filepath
    def changed(self):
        """return True if any template of this type has changed since self.timestamp"""
        for key, value in self.template.items():
            if datetime.fromtimestamp(getmtime(value)) > self.timestamp:
                logger.debug('Template {} has changed'.format(relpath(value, setting.layout)))
                self.reload = True
                return True
        return False
    def compile(self):
        for name, path in self.template.items():
            try:
                with open(path) as f:
                    text = f.read()
                setting.templates[name] = self.factory(text)
            except Exception as e:
                logger.error(c._("Error in template '{0}' in file {1}").format(name, path))
                logger.error(exception_report(e, ashtml=False))
    def load(self, all=False):
        if self.reload or all:
            self.find()
            self.compile()
        self.timestamp = datetime.now()
        self.reload = False

def templates_changed():
    """return True if any template of this type has changed since self.timestamp"""
    return any(loader.changed() for loader in template_loader.values())

def load_templates():
    """Read templates from layout directory.

    Read templates, compile them and store compiled templates in global variable 'templates'.

    Returns:
        None
    """
    template_types = list(template_loader.keys())
    if setting.debug > 1:
        logger.debug(c._('Scanning for templates in {0}').format(setting.layout))
        logger.debug(c._('Template types: {0}').format(' '.join(template_types)))
    for loader in template_loader.values():
        loader.load(all=True)

def reload_templates():
    """Reload templates from layout directory.

    Reload templates, compile them again and overwrite templates compiled earlier'.

    Returns:
        None
    """
    if setting.debug:
        logger.debug(c._('Reloading templates'))
    for loader in template_loader.values():
        loader.load()

# COMA template engine
from .coma import parse, Template

class ComaTemplateLoader(TemplateLoader):
    def compile(self):
        # partials are: _partials/FOO.hb => name = 'FOO'
        # templates are: FOO/bar.hb      => name = 'FOO_bar'
        for key, path in self.template.items():
            if key.startswith('_partial_'):
                name = key.replace('_partial_', '')
            else:
                name = key
            try:
                with open(path) as f:
                    text = f.read()
                setting.templates[name] = parse(text, name)
                if setting.tables and setting.debug > 1:
                    logger.debug(_("Template {} is in file {}"). \
                                 format(key, relpath(path, setting.layout)))
            except Exception as e:
                logger.error(_("Error in template '{0}' in file {1}").format(name, path))
                # logger.error(exception_report(e, ashtml=False))

add_template_type(ComaTemplateLoader('.hb', Template))

# Chameleon template engine
try:
    from chameleon import PageTemplate
except ImportError as e:
    logger.critical(c._('Chameleon template engine not available (%s)'), e)
    sys.exit(1)

class ChameleonTemplate(PageTemplate):
    def __call__(self, context):
        return self.render(this=context)
add_template_type(TemplateLoader('.pt', ChameleonTemplate))
