=========
hgwebinit
=========

`hgwebinit` is a Mercurial extension for hgweb that allows for remote creation
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

`hgwebinit` is available on bitbucket (primary) and github (mirror):

* https://bitbucket.org/j3hyde/hgwebinit
* https://github.com/j3hyde/hgwebinit

`hgwebinit` may be installed from the Python Package Index using::

	easy_install hgwebinit

or, via `pip`::

	pip install hgwebinit

This will download the current version of `hgwebinit` and get you ready.  Next
you will want to configure your hgweb installation to also use hgwebinit.  Here
is an `hgweb.ini` for example::

	[paths]
	/trunk=/repos/*

	[web]
	allow_push = *
	push_ssl = false
	allow_create = *

	[extensions]
	hgwebinit=

hgwebinit will allow for creation of new repositories within collections or as 
sub-repositories.  A direct conflict or a path outside of configure paths is 
denied.  In the above configuration, all users are allowed to create new 
repositories.  Set `allow_create` to a list of users a la `allow_push` to let 
those users create new repositories.

Responses to common objections
==============================
Although there are security implications in doing this, they are not the ones 
that most people think of.  When searching for ways to create repositories 
remotely you are presented a couple options.  One is to use hg via ssh.  The 
others basically consist of using bitbucket's web interface or similar.  New 
comers then often ask "what if I want to create a repository via http?"  They 
are almost always confronted with the answer of "you can't do that because it 
would be insecure."

Please understand that whenever you put a server up on the Internet you must be
conscious of security.  The mechanisms in place here are useful but not
complete.  Please take precautions to lock down your server and ensure the right
people are doing only things you have allowed them to do. 

Security: User permissions
--------------------------

The `hgweb` user has access to all the repositories and can't determine 
permission.

`hgweb` handles read permissions already despite that it is running as www-data, 
etc.  Given that you are using `hgweb` at all, file permissions have nothing to do
with it.  What is needed is a permission model for repository creation in 
addition to the current read.

Security: User authentication/authorization
-------------------------------------------

Permissions are in the domain of the web server, not `mercurial`.

Installations do leave authentication and some authorization to the web server 
(typically `Apache`) but hgweb actually does do some authorization on its own.  It
checks for the username of the authenticated user against the configured read 
and push groups.  What `mercurial` lacks is a permission for init.

Complexity: Protocol
--------------------
 
It would be adding to the protocol.

It would actually be bringing the HTTP protocol in line with what the SSH 
protocol already allows.  The first implementation of `hgwebinit` simply creates 
repositories implicitly.  This is actually somewhat scary but it's a first rev.  
The elegant solution may be treat init as a line protocol capability.  Any peer 
implementation can then be written to use that capability.

Complexity: Scope creep
-----------------------

This basically boils down to "if `hg` did that then people would want all this 
other stuff."

First off, that's a great problem to have.  Secondly, that should be a 
conversation that is prevented or controlled through the dissemination of 
information.  For instance, what is the impetus of the implementation and what 
is it designed to provide.  There are still many other options out there that 
provide more elegant ways to get the job done.  However, this doesn't mean that 
the baseline tool should have a blind spot compared to other parts of its own 
implementation (e.g. `SSH` peer).
