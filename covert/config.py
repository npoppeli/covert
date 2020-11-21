# -*- coding: utf-8 -*-
"""Objects and functions related to the configuration and the command line.

Attributes:
    config_default (dict): default values for configuration options
"""

import argparse, gettext, logging, sys
from importlib import import_module
from inspect import getmembers, isclass
from os import getcwd, mkdir
from os.path import join, exists, isfile, splitext
from . import setting
from .model import read_models, BareItem, ItemRef
from .view import read_views, Button
from .layout import load_templates
from .common import read_yaml_file, InternalError
from . import common as c
from .engine.hashfs import HashFS

logger = logging.getLogger('covert')

extra_arguments = {}

def add_argument(name, **options):
    global extra_arguments
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
                      username='', password='',
                      models='models', views='views', language='en')

def read_configuration():
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
        print(c._("Current directory does not contain a 'config' file"))
        sys.exit()
    if 'debug'    in config: setting.debug    = config['debug']
    if 'nostore'  in config: setting.nostore  = config['nostore']
    if 'verbose'  in config: setting.verbose  = config['verbose']
    setting.content  = join(setting.site, config['content'])
    setting.layout   = join(setting.site, config['layout'])
    setting.media    = join(setting.site, config['media'])
    setting.host     = config['host']
    setting.port     = config['port']
    setting.username = config['username']
    setting.password = config['password']
    setting.dbname   = config['dbname']
    setting.dbtype   = config['dbtype']

    # I18N
    setting.language = config['language']
    if setting.language != 'en':  # switch to application language
        app_trans = gettext.translation('covert', localedir=setting.locales,
                                        languages=[setting.language])
        c._ = app_trans.gettext

    # keep original configuration
    setting.config = config
    # in debugging mode, print some configuration parameters
    if setting.debug:
        logger.setLevel(logging.DEBUG)
    if setting.debug >= 2:
        logger.debug(c._("Debug option is {}").format(setting.debug))
        logger.debug(c._("Verbose option is {}").format(setting.verbose))
        logger.debug(c._("Changes are{}written to the database").format(c._(' *not* ') if setting.nostore else ' '))
        logger.debug(c._("Static content is in directory {}").format(setting.content))
        logger.debug(c._("User interface is in the '{}' language").format(setting.language))
        logger.debug(c._("Web server listens to {}:{}").format(setting.host, setting.port))

def initialize_kernel():
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
        raise InternalError(c._('Unknown storage engine: MongoDB and RethinkDB are supported'))
    init_storage()
    # initialize media storage
    if not exists(setting.media):
        mkdir(setting.media)
        logger.debug(c._('Created new folder for media storage: {}').format(setting.media))
    setting.media_db = HashFS(setting.media)
    if setting.debug >= 2:
        logger.debug(c._('Initialized content-addressable media storage'))

    # execute prelude (if present)
    if 'prelude' in setting.config:
        name, extension =  splitext(setting.config['prelude'])
        if extension == '.py':
            module_ = import_module(name)
        else:
            logger.info(c._('{} should be Python module').format(setting.config['prelude']))

    # read icons
    if 'icons' in setting.config:
        setting.icons.update(setting.config['icons'])

    # read templates
    load_templates()

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
                if issubclass(model_class, BareItem) or \
                        issubclass(model_class, ItemRef):
                    setting.models[class_name] = model_class
        elif extension == '.yml':
            models = read_yaml_file(item)
            read_models(models)
        else:
            logger.info(c._('{} should be in YAML or Python form').format(item))

    # import views
    name, extension = splitext(setting.config['views'])
    mod = import_module(name)
    read_views(mod)

    # now that we have the routes, labels and icons, we can create the buttons
    for route in setting.routes:
        button = Button(route.uid,
                        action=route.pattern, method=route.method,
                        vars=route.vars, name=route.name, param=route.param,
                        plabel=route.plabel, ptype=route.ptype, order=route.order)
        setting.buttons[route.uid] = button

    # print information about models and views
    if setting.tables:
        # print all routes (tabular)
        print(c._('Application has {0} routes').format(len(setting.routes)))
        fmt = "{:>5} {:<30} {:<10} {:<15} {:<20} {:<15} {:<30}"
        print(fmt.format('order', 'pattern', 'method', 'view', 'name', 'vars', 'templates'))
        print('-' * 125)
        for route in sorted(setting.routes, key=lambda r: r.order):
            print(fmt.format(route.order, route.pattern, route.method,
                             route.cls.__name__, route.name,
                             ', '.join(route.vars), ', '.join(route.templates)))
        print('')
        # print all buttons (tabular)
        print(c._('Application has {0} buttons').format(len(setting.buttons)))
        fmt = "{:<25} {:<15} {:<25} {:<35} {:<10} {:<15} {:<10}"
        print(fmt.format('uid', 'label', 'icon', 'action', 'method', 'vars', 'name'))
        print('-' * 140)
        for button in setting.buttons.values():
            print(fmt.format(button.uid, button.label, button.icon, button.action,
                             button.method, ', '.join(button.vars), button.name))
        print('')
        # print all models (tabular)
        print(c._('Application has {0} models').format(len(setting.models)))
        ref_classes = []
        for name in sorted(setting.models.keys()):
            if name.endswith('Ref'):
                ref_classes.append(name)
            else:
                model = setting.models[name]
                if not issubclass(model, BareItem):
                    print('{0} is not a sub-class of BareItem'.format(name))
                    continue
                print('{0}\n{1}'.format(name, '='*len(name)))
                fmt = "{:<15} {:<20} {:<10} {!s:<10} {!s:<10} {!s:<10} {!s:<10}"
                print(fmt.format('name', 'label', 'schema', 'optional',
                                 'multiple', 'auto', 'formtype'))
                print('-'*90)
                for field_name in model.fields:
                    meta = model.meta[field_name]
                    print(fmt.format(field_name, meta.label, meta.schema, meta.optional,
                                     meta.multiple, meta.auto, meta.formtype))
            print('')
