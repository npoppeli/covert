# -*- coding: utf-8 -*-
"""Objects and functions related to the configuration and the command line.

Attributes:
    config_default (dict): default values for configuration options
"""

import argparse, logging, sys
from importlib import import_module
from inspect import getmembers, isclass
from os import getcwd, mkdir
from os.path import join, exists, isfile, splitext
from . import setting
from .model import read_models
from .view import read_views
from .layout import read_templates
from .common import read_yaml_file, InternalError, logger
from .engine.hashfs import HashFS

extra_arguments = {}

def add_argument(name, **options):
    extra_arguments[name] = options

def parse_cmdline():
    """Parse command line

    Parse command line and return parsed argument list.
    Set global debug option if -d option present on command line.

    Returns:
        Namespace object: return value of parser.parse_args()
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config',  help='configuration', action='store',      default='config')
    parser.add_argument('-d', '--debug',   help='debug',         action='store_true', default=False)
    parser.add_argument('-n', '--nostore', help='dry run',       action='store_true', default=False)
    parser.add_argument('-t', '--tables',  help='tables',        action='store_true', default=False)
    parser.add_argument('-v', '--verbose', help='verbose',       action='store_true', default=False)
    for name, options in extra_arguments.items():
        parser.add_argument(name[1:3], name, **options)
    args = parser.parse_args()
    setting.config_file = args.config
    setting.debug   = args.debug
    setting.nostore = args.nostore
    setting.tables  = args.tables
    setting.verbose = args.verbose
    return args

config_default = dict(content='content', layout='layout', media='media',
                      dbname='test', dbtype='mongodb',
                      host='localhost', port='8080',
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
    else:
        logger.error("Current directory does not contain a 'config' file")
        sys.exit()
    if 'debug'   in config: setting.debug   = config['debug']
    if 'nostore' in config: setting.nostore = config['nostore']
    if 'verbose' in config: setting.verbose = config['verbose']
    if 'host'    in config: setting.host    = config['host']
    if 'port'    in config: setting.port    = config['port']
    setting.content = join(setting.site, config['content'])
    setting.layout  = join(setting.site, config['layout'])
    setting.media   = join(setting.site, config['media'])
    setting.store_dbname  = config['dbname']
    setting.dbtype  = config['dbtype']
    setting.language = config['language'] if config['language'] in setting.languages\
                       else config_default['language']
    # keep original configuration
    setting.config = config
    # in debugging mode, print some configuration parameters
    if setting.debug:
        logger.setLevel(logging.DEBUG)
    logger.debug("Debug option is {}".format(setting.debug))
    logger.debug("Verbose option is {}".format(setting.verbose))
    logger.debug("Changes are{}written to the database".format(' *not* ' if setting.nostore else ' '))
    logger.debug("Static content is in directory {}".format(setting.content))
    logger.debug("User interface is in the '{}' language".format(setting.language))
    logger.debug("Web server listens to {}:{}'".format(setting.host, setting.port))

def kernel_init():
    """Initialize kernel.

    Initialize various parts of kernel (storage, layout, models, views).
    Print debugging information if called with '-d' option.

    Returns:
        None
    """
    # initialize item storage
    if setting.dbtype == 'mongodb':
        from .engine.mongodb import init_storage
    elif setting.dbtype == 'rethinkdb':
        from .engine.rethinkdb import init_storage
    else:
        raise InternalError('Unknown storage engine: only MongoDB and RethinkDB are supported')
    init_storage()
    # initialize media storage
    if not exists(setting.media):
        mkdir(setting.media)
        logger.debug("Created new folder for media storage: {}".format(setting.media))
    setting.store_mdb = HashFS(setting.media)
    logger.debug("Initialized content-addressable media storage")

    # execute prelude (if present)
    if 'prelude' in setting.config:
        name, extension =  splitext(setting.config['prelude'])
        if extension == '.py':
            _ = import_module(name)
        else:
            logger.info('{} should be Python module'.format(setting.config['prelude']))

    # read templates
    read_templates()

    # import models
    if isinstance(setting.config['models'], list):
        model_list = setting.config['models']
    else:
        model_list = [setting.config['models']]
    for item in model_list:
        name, extension = splitext(item)
        if extension == '.py':
            mod = import_module(name)
            for class_name, model_class in getmembers(mod, isclass):
                if class_name in ['BareItem', 'Item', 'ItemRef']:
                    continue
                logger.debug('Adding/replacing class %s', class_name)
                setting.models[class_name] = model_class
        elif extension == '.yml':
            models = read_yaml_file(item)
            read_models(models)
        else:
            logger.info('{} should be in YAML or Python form'.format(item))

    # import views
    name, extension = splitext(setting.config['views'])
    mod = import_module(name)
    read_views(mod)

    # I18N
    label_index = setting.languages.index(setting.language)
    for name in setting.labels.keys():
        parts = setting.labels[name].split('|')
        setting.labels[name] = parts[label_index]

    # print information about models and views
    if setting.tables:
        # print all routes (tabular)
        print('Application has {0} routes'.format(len(setting.routes)))
        fmt = "{:>5} {:<30}: {:<10} {:<15} {:<20} {:<15} {:<30}"
        print(fmt.format('order', 'pattern', 'method', 'view', 'name', 'params', 'templates'))
        print('-' * 120)
        for route in sorted(setting.routes, key=lambda r: r.order):
            print(fmt.format(route.order, route.pattern, route.method,
                             route.cls.__name__, route.name,
                             ', '.join(route.params), ', '.join(route.templates)))
        print('')
        # print all models (tabular)
        print('Application has {0} models'.format(len(setting.models)))
        ref_classes = []
        for name in sorted(setting.models.keys()):
            if name.endswith('Ref'):
                ref_classes.append(name)
            else:
                model = setting.models[name]
                print('{0}\n{1}'.format(name, '='*len(name)))
                fmt = "{:<15}: {:<20} {:<10} {!s:<10} {!s:<10} {!s:<10} {!s:<10}"
                print(fmt.format('name', 'label', 'schema', 'optional',
                                 'multiple', 'auto', 'formtype'))
                print('-'*90)
                for field_name in model.fields:
                    meta = model.meta[field_name]
                    print(fmt.format(field_name, meta.label, meta.schema, meta.optional,
                                     meta.multiple, meta.auto, meta.formtype))
            print('')
        if ref_classes:
            print('Reference classes:', ', '.join(ref_classes))
