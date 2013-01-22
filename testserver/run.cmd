@echo Note: This assumes that we are running in an environment where hgweb-init is on the Python path and can be imported as an extension.  Nevermind, it's in the webconfig.  But, well, it shouldn't be...

set HGRCPATH=hgweb.ini
hg serve --web-conf=hgweb.ini
