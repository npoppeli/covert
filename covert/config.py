# -*- coding: utf-8 -*-
"""
covert.config
-----
Objects and functions related to configuration.
"""

import yaml

def load_config(path):
    with open(path, 'r') as file:
        config = yaml.load(file, Loader=yaml.CLoader)
    return config
