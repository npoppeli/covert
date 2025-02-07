#!/usr/bin/env python3

from setuptools import setup

setup(
    name='covert',
    version='0.9',
    author='Nico Poppelier',
    author_email='n.poppelier@xs4all.nl',
    license='MIT',
    url='http://schier7.home.xs4all.nl/covert',
    description='Web framework',
    long_description=
        "Covert is a storage-agnostic web framework.",
    download_url="http://schier7.home.xs4all.nl/covert/download",
    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: MIT License",
        'Operating System :: POSIX',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10'
    ],
    install_requires=[
        'chameleon>=3.0',
        'mongodb-org>=3.2', # plus mongo tools
        'pymongo>=3.0.0',
        'webOb>=1.7.0',
        'pyyaml>=5.1',
        'voluptuous>=0.10',
        'waitress>=1.0.0'
    ],
    packages=['covert']
)
