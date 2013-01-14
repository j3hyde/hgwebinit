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

def getLocalPathForVirtual(ui, path):
    pass

def path_is_a_repo(ui, path):
    pass

def should_create_repo(obj, req):   
    """Check if the requested repository exists and if this is a push request.
    """
    
    # we need to get the hgweb config so refresh first
    obj.refresh()
    
    # Determine the need for creation
    virtual = req.env.get("PATH_INFO", "").strip('/')
    
    # is this a request for a (non-existent) repo?
    if virtual.startswith('static/') or 'static' in req.form:
        return False
    
    # this is a request for the top level index?
    if not virtual:
        return False
    
    # is this a request for nested repos and hgwebs?
    repos = dict(obj.repos)
    virtualrepo = virtual
    while virtualrepo:
        real = repos.get(virtualrepo)
        if real:
            return False
        up = virtualrepo.rfind('/')
        if up < 0:
            break
        virtualrepo = virtualrepo[:up]

        
    # is this a request for subdirectories?
    subdir = virtual + '/'
    if [r for r in repos if r.startswith(subdir)]:
        return False


    # TODO: need a check to ensure requested path is within configured collections.


    # Okay, but should we proceed?  (basically restrict to push requests)
    # Push will do:
    #  * capabilities
    #  * heads
    #  * known nodes
    #  * list_keys (namespace=phases)
    #  * list_keys (namespace=bookmarks)
    
    # our capabilities are pretty much just unbundle until created...?    
    
    # If we've made it this far then we need to create a repo
    
    return True

    

    

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
        if should_create_repo(obj, req):
            # Ah, but is this user allowed to create repos?
            if create_allowed(obj.ui, req):
                # determine physical path based on config (paths setting)
                # if it doesn't fall into a configured collections or subrepo, then deny with 401
                virtual = req.env.get("PATH_INFO", "").strip('/') 
                
                    
                # init the repo
                print 'create repo at path=%s' % virtual
                #hg.repository(obj.ui, path=virtual, create=True)
                # force refresh
                obj.lastrefresh = 0    
                # add it to hgwebdir_mod? or have them push again?
                # obj.repos.append(virtual)
                
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
        raise ErrorResponse(HTTP_UNAUTHORIZED, 'create not authorized')

    allow_create = ui.configlist('web', 'allow_create', untrusted=True)
    result = (allow_create == ['*']) or (user in allow_create)
    if not result:
        raise ErrorResponse(HTTP_UNAUTHORIZED, 'create not authorized')

    return True






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
    
class Env(object):
    def __init__(self, env):
        self.env = env
        
    def get(self, key, default=None):
        if self.env.has_key(key):
            return self.env[key]
        else:
            return default
    
class UiMock(object):
    '''A simple Mock for hg's ui object that allows access to configuration
    information.'''
    
    def __init__(self, src=None, config=None):
        if config is None:
            config = {}
        self.config = config
        
    def configlist(self, section, name, default=[], untrusted=False):
        val = self.config[section].get(name, default)
        if type(val) != list:
            val = [val]
        return val
    
    def configbool(self, section, name, default=False, untrusted=False):
        return self.config.get(section, {}).get(name, default)
    
    def copy(self):
        return self.__class__(self)

    def readconfig(self, filename, root=None, trust=False,
                   sections=None, remap=None):
        pass
    
    def configitems(self, section, untrusted=False):
        s_dict = self.config.get(section, {})
        if s_dict is None:
            s_dict = {}
            
        return s_dict.items()

        
class RequestMock(object):
    '''A simple Mock for hg's Request object.  It allows access to environment
    variables.'''
    def __init__(self, env=None, form=None):
        self.env = env
        if env is None:
            self.env = {}
            
        self.form = form
        if form is None:
            self.form = {}
        

class ModuleMock(object):
    def __init__(self, ui):
        self.ui = ui
        self.repos = []
    
    def refresh(self):
        pass

class PermissionCheckTests(TempDirTestCase):
    '''Tests for user/client/connection permission to create repositories.'''
    def setUp(self):
        '''Set up some baseline configuration for hgwebinit.'''
        TempDirTestCase.setUp(self)
        self.default_config = {
                              'web': {
                                  'deny_create': ['deny_user'],
                                  'allow_create': ['allow_user'],
                                  'allow_push': '*'
                                  }
                               }
        self.ui = UiMock(config=self.default_config)
    
    def tearDown(self):
        '''Teardown.'''
        TempDirTestCase.tearDown(self)
    
    def testDenyNoSsl(self):
        self.assertRaises(ErrorResponse, create_allowed, self.ui, RequestMock(env={
                                              'REMOTE_USER': 'allow2_user',
                                              'REQUEST_METHOD': 'POST',
                                              'wsgi.url_scheme': 'http'
                                              }))
    
    def testDenyHttpGet(self):
        self.assertRaises(ErrorResponse, create_allowed, self.ui, RequestMock(env={
                                              'REMOTE_USER': 'allow2_user',
                                              'REQUEST_METHOD': 'GET',
                                              'wsgi.url_scheme': 'https'
                                              }))
    
    def testDenyCreate(self):
        self.assertRaises(ErrorResponse, create_allowed, self.ui, RequestMock(env={
                                              'REMOTE_USER': 'deny_user',
                                              'REQUEST_METHOD': 'POST',
                                              'wsgi.url_scheme': 'https'
                                              }))
    
    def testAllowCreate(self):
        self.assertTrue(create_allowed(self.ui, RequestMock(env={
                                             'REMOTE_USER': 'allow_user',
                                              'REQUEST_METHOD': 'POST',
                                              'wsgi.url_scheme': 'https'
                                              })))
    
    def testDefaultCreate(self):
        '''Test the case where the authenticated user isn't the list for either 
        of allow_create or deny_create but everything else passes.  The user
        should be denied, by default, from create a new repository.  Only 
        explicit permission will get the job done.'''
        self.assertRaises(ErrorResponse, create_allowed, self.ui, RequestMock(env={
                                              'REMOTE_USER': 'allow2_user',
                                              'REQUEST_METHOD': 'POST',
                                              'wsgi.url_scheme': 'https'
                                              }))
        self.assertRaises(ErrorResponse, create_allowed, self.ui, RequestMock(env={
                                              'REMOTE_USER': 'deny2_user',
                                              'REQUEST_METHOD': 'POST',
                                              'wsgi.url_scheme': 'https'
                                              }))

class RepoDetectionTests(TempDirTestCase):
    '''Tests for whether a repo should be created.'''
    
    def setUp(self):
        '''Set up some baseline configuration for hgwebinit.'''
        TempDirTestCase.setUp(self)
        
        import os.path
        
        collectiondir = self.make_temp_dir()
        manycollectiondir = self.make_temp_dir()
        tmprepo = self.make_temp_dir()
        
        self.default_config = {
            'web': {
                'deny_create': ['deny_user'],
                'allow_create': ['allow_user'],
                'allow_push': '*'
            },
            'paths': {
                '/trunk2/short' : os.path.join(collectiondir, '*'),
                '/trunk2/many' : os.path.join(manycollectiondir, '**'),
                '/trunk1' : tmprepo
            }
        }
        self.ui = UiMock(config=self.default_config)
    
    def tearDown(self):
        '''Teardown.'''
        TempDirTestCase.tearDown(self)
    
    def testNonRepoPathRequests(self):
        '''Given a URL for static resources, ensure the extension returns
        without creating a repo.'''
                
        req = RequestMock(env={
                          'REMOTE_USER': 'allow_user',
                          'REQUEST_METHOD': 'GET',
                          'wsgi.url_scheme': 'http'
                          })
        
        # static requests (no)
        req.env['PATH_INFO'] = '/static/mystylesheet.css'
        m = ModuleMock(self.ui)
        self.assertFalse(should_create_repo(m, req))
        
        req.form['static'] = True
        m = ModuleMock(self.ui)
        self.assertFalse(should_create_repo(m, req))
        
        # top-level index request (no)
        req.env['PATH_INFO'] = '/'
        m = ModuleMock(self.ui)
        self.assertFalse(should_create_repo(m, req))
        
        # repo request (no)
        req.env['PATH_INFO'] = '/trunk/test1/'
        m = ModuleMock(self.ui)
        repos = ['trunk/test1']
        m.repos += repos
        self.assertFalse(should_create_repo(m, req))
        
        # repo subdir request (no)
        req.env['PATH_INFO'] = '/trunk/test1/howdy.txt'
        m = ModuleMock(self.ui)
        repos = ['trunk/test1']
        m.repos += repos
        self.assertFalse(should_create_repo(m, req))
    
    def testRepoPathRequest(self):
        '''Given a request for an existing Repo, ensure the extension returns 
        without creating a repo.'''
        
        req = RequestMock(env={
                          'REMOTE_USER': 'allow_user',
                          'REQUEST_METHOD': 'GET',
                          'wsgi.url_scheme': 'http',
                          'PATH_INFO': '/trunk1'
                          })
        
        m = ModuleMock(self.ui)
        self.assertFalse(should_create_repo(m, req))
        
    
    def testNonPushRequest(self):
        '''For an otherwise acceptable, but non-push request, ensure the
        extension returns without creating a repo.'''
        self.assertTrue(False)
        
    def testCreateOnCollection(self):
        '''Allow for creation of repos within collections.
        Note: This is relying on repo detection to prevent a new repo from being
        created at the location of an existing one.'''
                
        req = RequestMock(env={
                          'REMOTE_USER': 'allow_user',
                          'REQUEST_METHOD': 'POST',
                          'wsgi.url_scheme': 'https'
                          })
        m = ModuleMock(self.ui)
        
        # Don't create a new repo at /trunk
        req.env['PATH_INFO'] = '/trunk2'
        self.assertFalse(should_create_repo(m, req))
        
        # Do create a new repo at /trunk/short/test1
        req.env['PATH_INFO'] = '/trunk2/short/test1'
        self.assertTrue(should_create_repo(m, req))
        
        # Do not create a new repo at /trunk/short/test2/test2
        req.env['PATH_INFO'] = '/trunk2/short/test2/test2'
        self.assertFalse(should_create_repo(m, req))
        
        # Do create a new repo at /trunk/many/test3
        req.env['PATH_INFO'] = '/trunk2/many/test3'
        self.assertTrue(should_create_repo(m, req))
        
        # Do create a new repo at /trunk/many/test4/test4
        req.env['PATH_INFO'] = '/trunk2/many/test4/test4'
        self.assertTrue(should_create_repo(m, req))
        
    def testCreateSubRepos(self):
        '''Allow for creation of sub-repos.'''
        self.assertTrue(False)