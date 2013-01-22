#!/usr/bin/env python

#mercurial hgweb support for repository creation.

import os.path
from setuptools import setup

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name='hgwebinit',
    version='0.1.0dev',
    description='Mercurial hgweb init support.',
    long_description=read('README.rst'),
    author='Jeffrey Kyllo',
    author_email='jkyllo@echospiral.com',
    url='https://bitbucket.org/j3hyde/hgwebinit',
    packages=['hgwebinit'],
    package_dir={'hgwebinit': 'src'},
    classifiers=[
        'Development Status :: 1 - Planning',
        'Environment :: Plugins',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Version Control',
    ]
)
