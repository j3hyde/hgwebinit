=========
hgwebinit
=========

*hgwebinit* is a Mercurial extension for hgweb that allows for remote creation
of repositories.  At this time hgwebinit creates repositories implicitly if the 
requesting user has permission to do so.  This can easily create repositories 
unintentionally if the user simply misspells a repo or path.  The primary use 
is for creating new repositories within collections but it is not currently 
limited to that.

Note that there are better tools out there for create repositories.  The goal of
this extension is to provide an easy-to-use option that gets the basic job done.
Feedback is certainly welcome as this is in an early stage.

The intent for future versions is to move to implementing tighter security
measures in the permission model and to potentially implement an init command in
the wire protocol.  This would prevent some confusion on the part of the user 
and allow for more fine-grained authorization.

Installation and Configuration
==============================

*hgwebinit* is available on bitbucket (primary) and github (mirror):

* https://bitbucket.org/j3hyde/hgwebinit
* https://github.com/j3hyde/hgwebinit

*hgwebinit* may be installed from the Python Package Index using::

	easy_install hgwebinit

or, via *pip*::

	pip install hgwebinit

This will download the current version of *hgwebinit* and get you ready.  Next
you will want to configure your hgweb installation to also use hgwebinit.  Here
is an *hgweb.ini* for example::

	[paths]
	/trunk=/repos/*

	[web]
	allow_push = *
	push_ssl = false
	allow_create = *
	implicit_init = true

	[extensions]
	hgwebinit=

hgwebinit will allow for creation of new repositories within collections or as 
sub-repositories.  A direct conflict or a path outside of configure paths is 
denied.  In the above configuration, all users are allowed to create new 
repositories.  Set *allow_create* to a list of users a la *allow_push* to let 
those users create new repositories.

Security and Implementation Considerations
==========================================
Although there are security implications in doing this, they are not the ones 
that most people think of.  When searching for ways to create repositories 
remotely you are presented a couple options.  One is to use hg via ssh.  The 
others basically consist of using bitbucket's web interface or similar.  New 
comers then often ask "what if I want to create a repository via http?"  They 
are almost always confronted with the answer of "you can't do that because it 
would be insecure."

Please understand that whenever you put a server up on the Internet you must be
conscious of security.  The mechanisms provided by this extension are useful but
not complete.  Please take precautions to lock down your server and ensure the
right people are doing only things you have allowed them to do. 

Security: User permissions (authorization)
------------------------------------------

*hgweb* runs as the web server user (e.g. www-data under many Apache
configurations) and file system-level permissions are only checked for that
user.  *hgweb* then does some permissions processing on top of that.

*hgweb* handles read and push permissions on a per-user basis given that the
user was authenticated at all.  What is needed is a permission model for
repository creation in addition to the current read and push permissions.  This
extension adds a configuration for *allow_create* and *deny_create*.  These are
similar to the existing *allow_push* and *deny_push* configurations.  In fact,
at present a user must have both read and create permission in order to create
a repository implicitly.

Note that when considering user permissions it is important to recognize the
roll of *hgweb*.  When using a repository via SSH or locally, authorization is
delegated to the file system on which the repository is stored.  If the user
cannot use hg to read/write the repository then that is it - mission failed.

In the case  of *hgweb*, relying on file system permissions is insufficient.
Instead *hgweb* implements its read and push permissions.  *hgweb* is acting as
an authorization layer for *hy*.  This is an important distinction because it is
unique to repositories hosted for HTTP access.  For that reason, *hgwebinit*
includes permission for initializing a new repository.

Lastly consider that a user who is accessing a repository locally (this also
applies to many SSH-based cases) has more access to the repository than they
would when accessing that same repository via HTTP.  In particular, *hgweb*
provides no method that would destroy information in the repository.  An
authenticated user can push new information and can read existing information
but they cannot remove commits or delete the repository.  Conversely any user
with file-system permissions to the repository can actually delete it entirely.
In this sense *hgweb* actually provides more protection for the repository.  

Security: User identity (authentication)
----------------------------------------

When using a remote repository it is important to consider that the 
authenticated user may not be the one identified in the commit log.  This is 
true of *mercurial* in general and is not specific to *hgweb* or *hgwebinit*.
Consider that authenticating via SSH gives someone full access to the
repository.  They can then commit using whatever name and email they wish.  If
this poses major risk for your project or organization then please consider the
extension for *mercurial* that allows for signing commits using gpg.
Alternatively an extension that verifies that the commit identity matches the
authenticated user would be quite handy.

Side Effects
------------
In the current state *hgwebinit* allows for creating new repositories but does
so implicitly.  When a properly authorized user tries to push to or read from a
path that doesn't match a repository, a new repository is created on the fly.
The requested operation is then completed as normal.  This means that any
properly authorized user who misspells a repository path is going to create a
new repository.

This comes back to the topic of destructive edits because removing the
problematic repository is now necessary.  With direct repository access one can
simply delete it.  Allowing such destructive access from the Internet is
probably not wise and it is not the intent of this extension to allow such
actions.  Repairing that situation should be handled by someone with sufficient
repository access.

Roadmap
=======

Protocol Complexity
-------------------

The roadmap for this extension includes an addition to the hg protocol in order
to support explicit creation of repositories.  In other words, we want a user
with this extension installed to be able to type
**hg init https://server.com/remote_repo**, get authenticated and authorized and
end up with a new repository, just as they asked.

Although this adds to the HTTP protocol it would essentially close a feature gap
when compared to the functionality afforded by SSH connections.  Consider that
a user with sufficient file system permissions is able to initialize a new
repository anywhere.

Hg Scope Creep
--------------

The issue with adding commands an functionality like this is that it could open
a door for new feature requests.

First consider that it would be a great problem to have.  Users desiring 
functionality either provides input to Hg developers or provides ideas for
extension authors.

Secondly, that scope creep could be prevented or controlled through the
dissemination of information.  The goal of *hgwebinit* is essentialy to gain
parity with the SSH implementation while retaining a reasonable level of
security.  Given that, other crazy-cool authorization mechanisms are outside the
scope of this extension and should be considered for development as new
projects.