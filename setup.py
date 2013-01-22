#!/usr/bin/env python

#mercurial hgweb support for repository creation.

from setuptools import setup

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(name='hgweb-init',
      version='0.1.0dev',
      description='Mercurial hgweb init support.',
      long_description=read('README.md'),
      author='Jeffrey Kyllo',
      author_email='jkyllo@echospiral.com',
      url='https://bitbucket.org/j3hyde/hgwebinit',
      packages=['hgwebinit'],
      package_dir={'hgwebinit': 'src'}
     )
