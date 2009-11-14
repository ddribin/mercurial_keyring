# -*- coding: utf-8 -*-

"""
Storing HTTP authentication passwords in keyring database.

Installation method(s):

1) in ~/.hgrc (or /etc/hgext/...)

[extensions]
...
hgext.mercurial_keyring = /path/to/mercurial_keyring.py

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

KEYRING_ENTRY_PFX = "Mercurial:%s"

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
    
    # return user, password
    return None, None
    
