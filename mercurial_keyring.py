# -*- coding: utf-8 -*-

"""
Storing HTTP authentication passwords in keyring database.

Installation method(s):

1) in ~/.hgrc (or /etc/hgext/...)

[extensions]
...
hgext.mercurial_keyring = /path/to/mercurial_keyring.py


2) Drop this file to hgext directory and in ~/.hgrc

[extensions]
hgext.mercurial_keyring =

"""

from mercurial import hg, repo, util
from mercurial.i18n import _
try:
	from mercurial.url import passwordmgr
except:
	from mercurial.httprepo import passwordmgr

import keyring
import getpass
from urlparse import urlparse

KEYRING_SERVICE = "Mercurial"

def monkeypatch_method(cls):
    def decorator(func):
        setattr(cls, func.__name__, func)
        return func
    return decorator

@monkeypatch_method(passwordmgr)
def find_user_password(self, realm, authuri):
    """
    keyring-based implementation of username/password query

    Passwords are saved in gnome keyring, OSX/Chain or other platform
    specific storage and keyed by the repository url
    """
    # Calculate the true url. authuri happens to contain things like
    # https://repo.machine.com/repos/apps/module?pairs=0000000000000000000000000000000000000000-0000000000000000000000000000000000000000&cmd=between
    parsed_url = urlparse(authuri)
    base_url = "%s://%s%s" % (parsed_url.scheme, parsed_url.netloc, parsed_url.path)
    print "find_user_password", realm, base_url
    

    # TODO: odczyt danych z cache w procesie

    # TODO: odczyt danych już obecnych w keyring-u

    if not self.ui.interactive():
       raise util.Abort(_('mercurial_keyring: http authorization required'))
    self.ui.write(_("http authorization required\n"))
    self.ui.status(_("realm: %s, url: %s\n" % (realm, base_url)))
    username = self.ui.prompt(_("user:"), default = None)
    password = self.ui.getpass(_("password for user %s:" % username))
    
    # TODO: zapis w keyringu

    # TODO: zapis w cache w procesie


    return username, password
    #return None, None
    
