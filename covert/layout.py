# -*- coding: utf-8 -*-
"""
covert.template
-----
Objects and functions related to templates.
"""

from os import chdir, listdir
from os.path import join, splitext
from glob import glob
from chameleon import PageTemplateFile
from .report import logger
from . import setting

def read_templates():
    """read templates from layout directory"""
    template_types = ['.xml', '.pt']
    logging.debug('Scanning for templates in {0}'.format(setting.layout))
    for filename in listdir(setting.layout):
        (name, extension) = splitext(filename)
        if extension in template_types: # other extensions are ignored
            try:
                setting.template[name] = PageTemplateFile(join(setting.layout, filename))
            except Exception as e:
                logging.debug('Error in template for {0} in file {1}'.format(name, filename))
                logging.debug(str(e))

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