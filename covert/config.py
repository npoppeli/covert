# -*- coding: utf-8 -*-
"""Objects and functions related to the configuration and the command line.

Attributes:
    config_default (dict): default values for configuration options
"""

import argparse, sys
from importlib import import_module
from inspect import getmembers, isclass
from os import getcwd
from os.path import join, exists, isfile, splitext
from . import setting
from .model import read_models
from .view import read_views
from .layout import read_templates
from .common import read_yaml_file, InternalError

def parse_cmdline():
    """Parse command line

    Parse command line and return parsed argument list.
    Set global debug option if -d option present on command line.

    Returns:
        Namespace object: return value of parser.parse_args()
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config',  help='configuration file', action='store', default='config')
    parser.add_argument('-d', '--debug',   help='debug',   action='store_true', default=False)
    parser.add_argument('-v', '--verbose', help='verbose', action='store_true', default=False)
    args = parser.parse_args()
    setting.config_file = args.config
    setting.debug = args.debug
    setting.verbose = args.verbose
    return args

config_default = dict(content='content', layout='layout',
                      models='models', views='views', language='en')

def read_config():
    """Read configuration file.

    Read configuration file and define global settings (variables in module 'setting')

    Returns:
        None
    """
    setting.site = getcwd() # assumption: cwd == site directory
    sys.path.insert(0, setting.site)
    config_file = join(setting.site, setting.config_file)
    config = config_default.copy()
    if exists(config_file) and isfile(config_file):
        doc0 = read_yaml_file(config_file)
        config.update(doc0)
    setting.content = join(setting.site, config['content'])
    if setting.debug:
        print('Static content is in {0}'.format(setting.content))
    setting.layout  = join(setting.site, config['layout'])
    setting.store_dbname  = config['dbname']
    setting.dbtype  = config['dbtype']
    setting.language = config['language'] if config['language'] in setting.languages\
                       else config_default['language']
    label_index = setting.languages.index(setting.language)
    if setting.debug:
        print("Config: language is '{}'".format(setting.language))
    for name in setting.labels.keys():
        parts = setting.labels[name].split('|')
        setting.labels[name] = parts[label_index]
    # save original configuration
    setting.config  = config

def kernel_init():
    """Initialize kernel.

    Initialize various parts of kernel (storage, layout, models, views).
    Print debugging information if called with '-d' option.

    Returns:
        None
    """
    # initialize storage
    if setting.dbtype == 'mongodb':
        from .engine.mongodb import init_storage
    elif setting.dbtype == 'rethinkdb':
        from .engine.rethinkdb import init_storage
    else:
        raise InternalError('Unknown storage engine: only MongoDB and RethinkDB are supported')
    init_storage()

    # read templates
    read_templates()

    # import models (YAML or Python)
    if isinstance(setting.config['models'], list):
        model_list = setting.config['models']
    else:
        model_list = [setting.config['models']]
    for item in model_list:
        name, extension = splitext(item)
        if extension == '.py':
            module = import_module(name)
            for class_name, model_class in getmembers(module, isclass):
                setting.models[class_name] = model_class
        elif extension == '.yml':
            models = read_yaml_file(item)
            read_models(models)
        else:
            print('{} not a valid option for models'.format(item))

    # import views (Python)
    name, extension = splitext(setting.config['views'])
    module = import_module(name)
    read_views(module)

    # print information about models and views
    if setting.debug:
        # print all routes (tabular)
        print('Application has {0} routes'.format(len(setting.routes)))
        fmt = "{:<25}: {:<10} {:<15} {:<10} {:<30}"
        print(fmt.format('pattern', 'method', 'view', 'route', 'templates'))
        print('-' * 90)
        for route in setting.routes:
            print(fmt.format(route.pattern, route.method, route.cls.__name__, route.name,
                           ', '.join(route.templates)))
        print('')
        # print all models (tabular)
        print('Application has {0} models'.format(len(setting.models)))
        for name in sorted(setting.models.keys()):
            if name.endswith('Ref'):
                print('Reference class', name)
            else:
                model = setting.models[name]
                print('{0}\n{1}'.format(name, '-'*len(name)))
                fmt = "{:<15}: {:<15} {:<10} {!s:<10} {!s:<10} {!s:<10} {!s:<10}"
                print(fmt.format('name', 'label', 'schema', 'optional',
                                 'multiple', 'auto', 'formtype'))
                print('-'*90)
                for field_name in model.fields:
                    meta = model.meta[field_name]
                    print(fmt.format(field_name, meta.label, meta.schema, meta.optional,
                                     meta.multiple, meta.auto, meta.formtype))
            print('')
