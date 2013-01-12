#mercurial hgweb support for repository creation.

#defining features:
# * Add configurations for create_allowed permission
# * Create a repository when none exists (if the user has permission)
# * Hook into hgweb check_authnz for create_allowed permission
# * Handle 404 for incoming changesets.


#!/usr/bin/env python

from distutils.core import setup

setup(name='hgweb-init',
      version='1.0dev',
      description='Mercurial hgweb init support',
      author='Jeffrey Kyllo',
      author_email='jkyllo@echospiral.com',
      url='https://echospiral.com/trac/hgweb-init',
      packages=['hgwebinit'],
     )