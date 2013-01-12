# Licensed under the GPL v2 in accordance with the Mercurial license.
# Copyright 11 January 2013 Jeffrey Kyllo <jkyllo@echospiral.com>

import shutil
import tempfile
import unittest

cmdtable = {
            
}

def extsetup():
    pass

def create_allowed(ui, req):
    """Check allow_create and deny_create config options of a repo's ui object
    to determine user permissions.  By default, with neither option set (or
    both empty), deny all users to create new repos.  There are two ways a
    user can be denied create access:  (1) deny_create is not empty, and the
    user is unauthenticated or deny_create contains user (or *), and (2)
    allow_create is not empty and the user is not in allow_create.  Return True
    if user is allowed to read the repo, else return False."""

    user = req.env.get('REMOTE_USER')

    deny_create = ui.configlist('web', 'deny_create', untrusted=True)
    if deny_create and (not user or deny_create == ['*'] or user in deny_create):
        return False

    allow_create = ui.configlist('web', 'allow_create', untrusted=True)
    # by default, den creating if no allow_create option has been set
    if (allow_create == ['*']) or (user in allow_create):
        return True

    return False

class TempDirTestCase(unittest.TestCase):

    def setUp(self):
        self._on_teardown = []

    def make_temp_dir(self):
        temp_dir = tempfile.mkdtemp(prefix="tmp-%s-" % self.__class__.__name__)
        def tear_down():
            shutil.rmtree(temp_dir)
        self._on_teardown.append(tear_down)
        return temp_dir

    def tearDown(self):
        for func in reversed(self._on_teardown):
            func()
    
class NewRepositoryTests(TempDirTestCase):
    pass