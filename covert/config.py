# -*- coding: utf-8 -*-
"""
covert.config
-----
Objects and functions related to configuration.
"""

import argparse, sys
from yaml import load
try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader

from . import setting, storage
from .model import register_models

def read_cmdline():
    """read command line, return parsed argument list"""
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--debug',  help='debug',  action='store_true', default=False)
    parser.add_argument('-m', '--models', help='models', action='store_true', default=False)
    parser.add_argument('-r', '--routes', help='routes', action='store_true', default=False)
    args = parser.parse_args()
    setting.debug  = args.d
    setting.models = args.m
    setting.routes = args.r
    return args

def read_config(path):
    """read configuration file, define global settings"""
    with open(path, 'r') as f:
        config = load(f, Loader=Loader)
    setting.sitedir = sys.path[0]
    setting.config = config

# TODO: stores should be in a separate file identified in config.yml
# TODO: kernel.init() should be enough, and all registers should be in the kernel object

def kernel_init():
    storage.init_storage()
    register_models(setting.config['model'], storage.Item)
    setting.layout = setting.sitedir + '/' + setting.config['layout']['directory']
    setting.assets = setting.sitedir + '/' + setting.config['assets']['directory']
    setting.server = setting.config['server']
    if setting.routes:
        print('Application has {0} routes'.format(len(routes_map)))
        for action in action_map:
            regex = action[0].pattern
            method = action[1]
            cname = action[2].__self__.__class__.__name__
            mname = action[2].__name__
            print('{0} {1} -> {2}:{3}'.format(regex, method, cname, mname))
    if setting.models:
        print('Application has {0} model classes'.format(len(model_map)))
        for name, model in model_map.items():
            skeleton = model.skeleton
            print('{0}\n{1}'.format(name, '-'*len(name)))
            print(str(model.schema))
            for field_name, field in model.skeleton.items():
                print('{0}: "{1}" optional={2} multiple={3}'.\
                      format(field_name, field.label, field.optional, field.multiple))
            print('')
