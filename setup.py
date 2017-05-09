#!/usr/bin/env python3

from setuptools import setup

setup(
    name='covert',
    version='0.7',
    author='Nico Poppelier',
    author_email='n.poppelier@xs4all.nl',
    license='MIT',
    url='http://schier7.home.xs4all.nl/bass',
    description='Web framework',
    long_description=
        "Covert is a storage-agnostic web framework.",
    download_url="http://schier7.home.xs4all.nl/covert/download",
    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: MIT License",
        'Operating System :: POSIX',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
    ],
    install_requires=[
        'Chameleon>=2.18',
        'pymongo>=3.0.0',
        'webOb>=1.5.0'
    ],
    packages=['covert']
)
