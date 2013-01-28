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

from mercurial.i18n import _
from mercurial import hg, extensions, encoding, templater, wireproto, httppeer, ui
from mercurial.hgweb import hgwebdir_mod, protocol
from mercurial.hgweb.common import ErrorResponse, HTTP_UNAUTHORIZED
from mercurial.hgweb.common import HTTP_METHOD_NOT_ALLOWED, HTTP_FORBIDDEN

def should_create_repo(obj, req):   
    """Check if the requested repository exists and if this is a push request.
    """
        
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

    # Check to ensure requested path is within configured collections.
    paths = {}
    for name, value in obj.ui.configitems('paths'):
        paths[name] = value
    if not path_is_in_collection(virtual, paths):
        return False

    # If we've made it this far then it makes sense to create a repo
    return True

class emptyrepo(object):
    '''Provide an empty repo for basic protocol methods.  Basically just retains
    a ui object.'''
    def __init__(self, baseui=None):
        if baseui == None:
            baseui = ui.ui()
        self.ui = baseui
        self.requirements = set()
        self.supportedformats = set()
    def filtered(self, *args, **kwargs):
        return self

def hgwebinit_run_wsgi_wrapper(orig, obj, req):
    """Handles hgwebdir_mod requests, looking for pushes to non-existent repos.
    If one is detected, the user is first authorized and then prompted to init.
    Following that we simply hand the request off ot the next handler in the
    chain - typically hgwebdir_mod itself."""
    try:
        tmpl = obj.templater(req)
        ctype = tmpl('mimetype', encoding=encoding.encoding)
        ctype = templater.stringify(ctype)
        
        obj.refresh()
        
        # Do our stuff...
        if should_create_repo(obj, req):
            # Ah, but is this user allowed to create repos?
            if create_allowed(obj.ui, req):
                virtual = req.env.get("PATH_INFO", "").strip('/')
                
                paths = {}
                for name, value in obj.ui.configitems('paths'):
                    paths[name] = value
                 
                local = local_path_for_repo(virtual, paths)
                
                if obj.ui.configbool('web', 'implicit_init', False):
                    # Go ahead and init if implicit creation is enabled
                    hg.repository(obj.ui, path=local, create=True)
                else:
                    # Find out what the client wants.
                    # Only the capabilities and init commands are supported.
                    cmd = req.form.get('cmd', [''])[0]
                    if protocol.iscmd(cmd) and cmd in ('capabilities', 'init'):
                        repo = emptyrepo(baseui=obj.ui)
                        return protocol.call(repo, req, cmd)
                
                # force refresh
                obj.lastrefresh = 0    
                
    except ErrorResponse, err:
        req.respond(err, ctype)
        return tmpl('error', error=err.message or '')
    
    # Now hand off the request to the next handler (likely hgwebdir_mod)
    return orig(obj, req)

def http_peer_instance(orig, ui, path, create):
    '''A wrapper for hg.httppeer.instance that supports creating repositories.'''
    if create:
        if path.startswith('https:'):
            inst = httppeer.httpspeer(ui, path)
        else:
            inst = httppeer.httppeer(ui, path)
        inst.requirecap('init', _('repo init'))
        inst._call('init')
    else:
        inst = orig(ui, path, create)
    
    return inst

def hgproto_init(repo, proto):
    '''An hg protocol command handler that creates a new repository.  This gets
    bound to the 'init' command.'''
    virtual = proto.req.env.get("PATH_INFO", "").strip('/')
                
    paths = {}
    for name, value in repo.ui.configitems('paths'):
        paths[name] = value
     
    local = local_path_for_repo(virtual, paths)
    hg.repository(repo.ui, path=local, create=True)

def hgproto_capabilities(orig, repo, proto):
    '''A wrapper for hg.wireproto.capabilities that splices in 'init' as a
    supported capability.  Note that this only means the server is capable.  It
    is still possible for a client to get an error if the path is not supported.
    '''
    caps = orig(repo, proto)
    caps = ' '.join((caps, 'init'))
    return caps

def uisetup(ui):
    '''Hooks into hgwebdir_mod's run_wsgi method so that we can listen for
    requests.'''
    # wrap hgwebdir_mod so that we can handle creation
    extensions.wrapfunction(hgwebdir_mod.hgwebdir, 'run_wsgi', hgwebinit_run_wsgi_wrapper)
    
    # wrap up caps
    extensions.wrapfunction(wireproto, 'capabilities', hgproto_capabilities)
    
    # Need to reset the capabilities command to use our newly set up wrapper    
    wireproto.commands['capabilities'] = (wireproto.capabilities, '')
    wireproto.commands['init'] = (hgproto_init, '')

    # wrap http client to include ability to create
    extensions.wrapfunction(httppeer, 'instance', http_peer_instance) 

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
    #if req.env['REQUEST_METHOD'] != 'POST':
    #    msg = 'push requires POST request' 
    #    raise ErrorResponse(HTTP_METHOD_NOT_ALLOWED, msg)

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


def path_is_subrepo(path, conf_paths):
    '''Checks, in a basic fashion, whether the given path is considered to be
    a sub-repository.  This check is based solely on the hgweb-configured paths
    and does not verify actual repository structure.'''
    for virt in conf_paths:
        local = conf_paths[virt]
        
        # Skip if the path is an exact match
        if path == virt:
            continue
        
        # Skip if this configured path is a collection
        if local.endswith('**') or local.endswith('*'):
            continue
        
        # Check if the path is in this collection
        if path.startswith(virt):
            return True
      
    # After checking all the configured collections, there was no match  
    return False

def path_is_in_collection(path, conf_paths):
    '''Checks if path is contained within a set of given collection paths.  A 
    path is considered to be contained only if it is in a collection and only if
    the configured collection depth is appropriate for the path given.
    
    >>>path_is_in_collection('/', [('/howdy'], '/home/repos/howdy'))
    False
    >>>path_is_in_collection('/howdy', [('/howdy', '/home/repos/howdy')])
    False
    >>>path_is_in_collection('/howdy/hithere', [('/howdy', '/home/repos/*')])
    True
    >>>path_is_in_collection('/howdy/hithere/hello', [('/howdy', '/home/repos/*')])
    False
    >>>path_is_in_collection('/howdy/hithere/hello', [('/howdy', '/home/repos/**)'])
    True
    
    @param conf_paths: A dictionary of virtual-paths to local filesystem paths.
    '''
    
    # Assume some root path (since the config is written that way)
    if path[0] != '/':
        path = '/' + path
    
    # Check the path against each configured path.
    for virt in conf_paths:
        local = conf_paths[virt]
        
        # Skip if this configured path is not a collection
        if not (local.endswith('**') or local.endswith('*')):
            continue
        
        # Check if the path is in this collection
        if path.startswith(virt):
            return True
      
    # After checking all the configured collections, there was no match  
    return False

def local_path_for_repo(path, conf_paths):
    '''Determines the local file system path based on a given virtual (url) path
    and the hgweb path configuration.'''
    import os.path
    
    if path[0] != '/':
        path = '/' + path
    
    for virt in conf_paths:
        local = conf_paths[virt]
        
        # We can't put a repo at the root of a collection
        if local.endswith('*') and path == virt:
            continue
        
        # Let's not confuse collection paths
        if local.endswith('**'):
            local = local[:-3]
        elif local.endswith('*'):
            local = local[:-2]
        
        # Return the local path for the virtual one
        # Basically just remove the collection root from the virtual path and
        # replace it with the collection's local path
        if path.startswith(virt):
            p = os.path.normpath(path)
            v = os.path.normpath(virt)
            local = os.path.normpath(local)
            l = p.replace(v, local, 1)
            return l
      
    # After checking all the configured collections, there was no match  
    return None


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
    '''Tests for whether a repo should be created.  Assumes that request
    parameters are normal (POST with SSL).'''
    
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
        
        self.req = RequestMock(env={
            'REMOTE_USER': 'allow_user',
            'REQUEST_METHOD': 'POST',
            'wsgi.url_scheme': 'https'
        })
        
        self.ui = UiMock(config=self.default_config)
        
        self.mod = ModuleMock(self.ui)
        self.mod.repos = ['/trunk1']
    
    def tearDown(self):
        '''Teardown.'''
        TempDirTestCase.tearDown(self)
        
    def checkPath(self, path, mod=None, req=None):
        if mod is None:
            mod = self.mod
            
        if req is None:
            req = self.req
        
        req.env['PATH_INFO'] = path
        return should_create_repo(mod, req)
    
    def checkInCollection(self, path, ui=None):
        if ui is None:
            ui = self.ui
        
        return path_is_in_collection(path, ui.config['paths'])
        
    
    def testNonRepoPathRequests(self):
        '''Given a URL for static resources, ensure the extension returns
        without creating a repo.'''
                
        
        
        # static requests (no)
        self.assertFalse(self.checkPath('/static/mystylesheet.css'))
        
        req = RequestMock(env={
                          'REMOTE_USER': 'allow_user',
                          'REQUEST_METHOD': 'POST',
                          'wsgi.url_scheme': 'https'
                          },
                          form={
                                'static': True
                          })
        self.assertFalse(self.checkPath('/', req=req))
        
        # top-level index request (no)
        self.assertFalse(self.checkPath('/'))
        
        # repo request (no)
        m = ModuleMock(self.ui)
        repos = [('trunk/test1', '')]
        m.repos += repos
        self.assertFalse(self.checkPath('/trunk/test1/', mod=m))
        
        # repo subdir request (no)
        m = ModuleMock(self.ui)
        repos = [('trunk/test1', '')]
        m.repos += repos
        self.assertFalse(self.checkPath('/trunk/test1/howdy.txt', mod=m))
    
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
        pass
        
        
    def testPathConflict(self):
        # Don't create a new repo at /trunk2 - must be a subpath of a collection
        #self.assertFalse(self.checkPath('/trunk2'))
        self.assertFalse(self.checkInCollection('/trunk2'))
        
    def testShallowChildOnShortCollection(self):
        # Do create a new repo at /trunk/short/test1
        #self.assertTrue(self.checkPath('/trunk2/short/test1'))
        self.assertTrue(self.checkInCollection('/trunk2/short/test1'))
        
    def testDeepChildOnShortCollection(self):
        # Do not create a new repo at /trunk/short/test2/test2
        #self.assertFalse(self.checkPath('/trunk2/short/test2/test2'))
        self.assertTrue(self.checkInCollection('/trunk2/short/test2/test2')) 
        
    def testShallowChildOnDeepCollection(self):
        # Do create a new repo at /trunk/many/test3
        #self.assertTrue(self.checkPath('/trunk2/many/test3'))
        self.assertTrue(self.checkInCollection('/trunk2/many/test3'))
        
    def testDeepChildOnDeepCollection(self):
        # Do create a new repo at /trunk/many/test4/test4
        #self.assertTrue(self.checkPath('/trunk2/many/test4/test4'))
        self.assertTrue(self.checkInCollection('/trunk2/many/test4/test4'))
        
    def testNonCollectionConflict(self):
        self.assertFalse(self.checkInCollection('/trunk1'))
        
    def testChildAtRoot(self):
        self.assertFalse(self.checkInCollection('/test1'))
        
    def testSubRepo(self):
        '''Sub-repos must still be in a collection.'''
        self.assertFalse(self.checkInCollection('/trunk1/newrepo'))
        
    def testSubRepoInCollection(self):
        self.assertTrue(self.checkInCollection('/trunk2/many/test1/newrepo'))
        
class RepoPathCreationTests(TempDirTestCase):
    def setUp(self):
        TempDirTestCase.setUp(self)
        
        import os.path
        
        self.collectiondir = self.make_temp_dir()
        self.manycollectiondir = self.make_temp_dir()
        self.tmprepo = self.make_temp_dir()
        
        self.paths = {
                '/trunk2/short' : os.path.join(self.collectiondir, '*'),
                '/trunk2/many' : os.path.join(self.manycollectiondir, '**'),
                '/trunk1' : self.tmprepo
        }
        
    def checkPath(self, path, conf_paths=None):
        if conf_paths is None:
            conf_paths = self.paths
            
        return local_path_for_repo(path, conf_paths)
        
    def testRootPath(self):
        '''Local path for a non-configured repo returns None.'''
        self.assertEqual(None, self.checkPath('/test1'))
        
    def testShallowContainedPath(self):
        import os.path
        self.assertEqual(os.path.join(self.collectiondir, 'test1'), self.checkPath('/trunk2/short/test1'))
        
    def testDeepContainedPath(self):
        import os.path
        self.assertEqual(os.path.join(self.collectiondir, 'test1', 'test2'), self.checkPath('/trunk2/short/test1/test2'))
        
    def testSubRepoPath(self):
        import os.path
        self.assertEqual(os.path.join(self.tmprepo, 'test1', 'test2'), self.checkPath('/trunk1/test1/test2'))
        
class SubRepoTests(TempDirTestCase):
    def setUp(self):
        TempDirTestCase.setUp(self)
        
        import os.path
        
        self.collectiondir = self.make_temp_dir()
        self.manycollectiondir = self.make_temp_dir()
        self.tmprepo = self.make_temp_dir()
        
        self.paths = {
                '/trunk2/short' : os.path.join(self.collectiondir, '*'),
                '/trunk2/many' : os.path.join(self.manycollectiondir, '**'),
                '/trunk1' : self.tmprepo
        }
    
    def testPathIsSubRepo(self):
        self.assertTrue(path_is_subrepo('/trunk1/test1', self.paths))
        self.assertTrue(path_is_subrepo('/trunk1/test1/test2', self.paths))
    
    def testPathIsRepo(self):
        self.assertFalse(path_is_subrepo('/trunk1', self.paths))
    
    def testPathIsInCollection(self):
        self.assertFalse(path_is_subrepo('/trunk2/short/howdy1', self.paths))
        self.assertFalse(path_is_subrepo('/trunk2/many/howdy1', self.paths))
        self.assertFalse(path_is_subrepo('/trunk2/many/howdy1/howdy2', self.paths))
    
    def testPathAtRoot(self):
        self.assertFalse(path_is_subrepo('/', self.paths))
        self.assertFalse(path_is_subrepo('/test1', self.paths))