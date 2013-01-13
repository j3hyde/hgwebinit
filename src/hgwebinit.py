# Licensed under the GPL v2 in accordance with the Mercurial license.
# Copyright 11 January 2013 Jeffrey Kyllo <jkyllo@echospiral.com>

'''An extension for hgweb that allows for repository creation.  Since the hg
wire protocol does not currently have support for doing remote init via HTTP,
this extension instead watches for push requests to non-existent repositories
and prompts the (duely authorized) user to create it.  Following that the push
continues as expected.'''

import shutil
import tempfile
import unittest

from mercurial import hg, extensions, encoding, templater
from mercurial.hgweb import hgwebdir_mod
from mercurial.hgweb.common import ErrorResponse, HTTP_UNAUTHORIZED
from mercurial.hgweb.common import HTTP_METHOD_NOT_ALLOWED, HTTP_FORBIDDEN


def handle_repo_creation(obj, req):   
    """Check if the requested repository exists and if this is a push request.
    If so, then check if the user is allowed to create repositories, prompt to 
    create it, and do so if asked.
    
    In general, behave like hgwebdir_mod if at all possible."""
    

    # we need to get the hgweb config so refresh first
    print 'obj.refresh()'
    obj.refresh()
    
    # Determine the need for creation
    print 'get virtual'
    virtual = req.env.get("PATH_INFO", "").strip('/')
    
    # is this a request for a (non-existent) repo?
    print 'check for static'
    if virtual.startswith('static/') or 'static' in req.form:
        return
    
    # this is a request for the top level index?
    print 'non-virtual'
    if not virtual:
        return
    
    # is this a request for nested repos and hgwebs?
    print 'Check for repos'
    repos = dict(obj.repos)
    virtualrepo = virtual
    while virtualrepo:
        real = repos.get(virtualrepo)
        if real:
            return
        up = virtualrepo.rfind('/')
        if up < 0:
            break
        virtualrepo = virtualrepo[:up]

        
    # is this a request for subdirectories?
    print 'Check for subdirs'
    subdir = virtual + '/'
    if [r for r in repos if r.startswith(subdir)]:
        return

    # Okay, but should we proceed?  (basically restrict to push requests)
    # Push will do:
    #  * capabilities
    #  * heads
    #  * known nodes
    #  * list_keys (namespace=phases)
    #  * list_keys (namespace=bookmarks)
    
    # our capabilities are pretty much just unbundle until created...?
    

    # Ah, but is this user allowed to create repos?
    print 'create_allowed()'
    if not create_allowed(obj.ui, req):
        print 'not allowed: %s' % req.env.get('REMOTE_USER')
        return
    
    
    
    # If we've made it this far then we need to create a repo
    
    # determine physical path based on config (paths setting)
    # if it doesn't fall into a configured collections or subrepo, then deny with 401
    
    # init the repo
    print 'creating repository at path: %s' % virtual
    
    #hg.repository(obj.ui, path=virtual, create=True)

    # force another refresh
    obj.lastrefresh = 0    
    #obj.refresh()
    # add it to hgwebdir_mod? or have them push again?
    
    

    

def hgwebinit_run_wsgi_wrapper(orig, obj, req):
    """Handles hgwebdir_mod requests, looking for pushes to non-existent repos.
    If one is detected, the user is first authorized and then prompted to init.
    Following that we simply hand the request off ot the next handler in the
    chain - typically hgwebdir_mod itself."""
    try:
        tmpl = obj.templater(req)
        ctype = tmpl('mimetype', encoding=encoding.encoding)
        ctype = templater.stringify(ctype)
        
        # Do our stuff...
        handle_repo_creation(obj, req)
    except ErrorResponse, err:
        req.respond(err, ctype)
        return tmpl('error', error=err.message or '')
    
    # Now hand off the request to the next handler (likely hgwebdir_mod)
    return orig(obj, req)

def uisetup(ui):
    '''Hooks into hgwebdir_mod's run_wsgi method so that we can listen for
    requests.'''
    extensions.wrapfunction(hgwebdir_mod.hgwebdir, 'run_wsgi', hgwebinit_run_wsgi_wrapper)

def create_allowed(ui, req):
    '''Check allow_create and deny_create config options of a repo's ui object
    to determine user permissions.  By default, with neither option set (or
    both empty), deny all users to create new repos.  There are two ways a
    user can be denied create access:  (1) deny_create is not empty, and the
    user is unauthenticated or deny_create contains user (or *), and (2)
    allow_create is not empty and the user is not in allow_create.  Return True
    if user is allowed to read the repo, else return False.
    
    This is modeled on (copied almost verbatim) hg's read_allowed function.'''

    user = req.env.get('REMOTE_USER')
    
    allowpull = ui.configbool('web', 'allowpull')

    deny_read = ui.configlist('web', 'deny_read')
    if deny_read and (not user or deny_read == ['*'] or user in deny_read):
        raise ErrorResponse(HTTP_UNAUTHORIZED, 'read not authorized')

    allow_read = ui.configlist('web', 'allow_read')
    result = (not allow_read) or (allow_read == ['*'])
    if not (result or user in allow_read):
        raise ErrorResponse(HTTP_UNAUTHORIZED, 'read not authorized')

    if not allowpull:
        raise ErrorResponse(HTTP_UNAUTHORIZED, 'pull not authorized')
    
    # enforce that you can only push using POST requests
    if req.env['REQUEST_METHOD'] != 'POST':
        msg = 'push requires POST request'
        raise ErrorResponse(HTTP_METHOD_NOT_ALLOWED, msg)

    # require ssl by default for pushing, auth info cannot be sniffed
    # and replayed
    scheme = req.env.get('wsgi.url_scheme')
    if ui.configbool('web', 'push_ssl', True) and scheme != 'https':
        raise ErrorResponse(HTTP_FORBIDDEN, 'ssl required')

    deny = ui.configlist('web', 'deny_push')
    if deny and (not user or deny == ['*'] or user in deny):
        raise ErrorResponse(HTTP_UNAUTHORIZED, 'push not authorized')

    allow = ui.configlist('web', 'allow_push')
    result = allow and (allow == ['*'] or user in allow)
    if not result:
        raise ErrorResponse(HTTP_UNAUTHORIZED, 'push not authorized')


    deny_create = ui.configlist('web', 'deny_create', untrusted=True)
    if deny_create and (not user or deny_create == ['*'] or user in deny_create):
        return False

    allow_create = ui.configlist('web', 'allow_create', untrusted=True)
    # by default, den creating if no allow_create option has been set
    if (allow_create == ['*']) or (user in allow_create):
        return True

    # TODO: need a check to ensure requested path is within configured collections.

    return False






# Tests...

class TempDirTestCase(unittest.TestCase):
    '''Base class for TestCases that allows for easily creating temporary
    directories and automatically deletes them on tearDown.'''

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
    
class UiMock(object):
    '''A simple Mock for hg's ui object that allows access to configuration
    information.'''
    class Env(object):
        def __init__(self, env):
            self.env = env
            
        def get(self, key, default=None):
            if self.env.has_key(key):
                return self.env[key]
            else:
                return default
    
    def __init__(self, config):
        self.config = config
        
    def configlist(self, section, name, default=None):
        key = '%s:%s' % (section, name)
        if self.config.has_key(key):
            return self.config[key]
        else:
            return default
    
class RequestMock(object):
    '''A simple Mock for hg's Request object.  It allows access to environment
    variables.'''
    def __init__(self, env=None):
        self.env = env
        if env is None:
            self.env = {}
    
class NewRepositoryTests(TempDirTestCase):
    '''Tests for creation of new repositories.'''
    def setUp(self):
        '''Set up some baseline configuration for hgwebinit.'''
        self.ui = UiMock({
                          'web:deny_create': ['deny_user'],
                          'web:allow_create': ['allow_user'],
                          })
    
    def tearDown(self):
        '''Teardown.'''
        TempDirTestCase.tearDown(self)
    
    def testDenyCreate(self):
        self.assertFalse(create_allowed(self.ui, RequestMock(env={'REMOTE_USER': 'deny_user'})))
    
    def testAllowCreate(self):
        self.assertTrue(create_allowed(self.ui, RequestMock(env={'REMOTE_USER': 'allow_user'})))
    
    def testDefaultCreate(self):
        self.assertFalse(create_allowed(self.ui, RequestMock(env={'REMOTE_USER': 'allow2_user'})))
        self.assertFalse(create_allowed(self.ui, RequestMock(env={'REMOTE_USER': 'deny2_user'})))
        
    def testStaticPathRequest(self):
        '''Given a URL for static resources, ensure the extension returns
        without creating a repo.'''
        pass
    
    def testRepoPathRequest(self):
        '''Given a request for a Repo, ensure the extension returns without
        creating a repo.'''
        pass
    
    def testNonPushRequest(self):
        '''For an otherwise acceptable, but non-push request, ensure the
        extension returns without creating a repo.'''
        pass 