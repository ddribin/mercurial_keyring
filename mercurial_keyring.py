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

#import mercurial.demandimport
#mercurial.demandimport.disable()

from mercurial import hg, repo, util
from mercurial.i18n import _
try:
	from mercurial.url import passwordmgr
except:
	from mercurial.httprepo import passwordmgr

import keyring
import getpass
from urlparse import urlparse
import urllib2

KEYRING_SERVICE = "Mercurial"

############################################################

def monkeypatch_class(name, bases, namespace):
    """http://mail.python.org/pipermail/python-dev/2008-January/076194.html"""
    assert len(bases) == 1, "Exactly one base class required"
    base = bases[0]
    for name, value in namespace.iteritems():
        if name != "__metaclass__":
           setattr(base, name, value)
    return base

def monkeypatch_method(cls):
    def decorator(func):
        setattr(cls, func.__name__, func)
        return func
    return decorator

############################################################

class PasswordStore(object):
    """
    Helper object handling password save&restore. Passwords
    are saved both in local memory cache, and keyring, and are
    restored from those.
    """
    def __init__(self):
        self.cache = dict()
    def save_password(self, url, username, password):
        self.cache[url] = (username, password)
        # TODO: keyring save
    def get_password(self, url):
        r = self.cache.get(url)    
        if r:
           return r
        # TODO: keyring restore
        return None, None

password_store = PasswordStore()

############################################################

@monkeypatch_method(passwordmgr)
def find_user_password(self, realm, authuri):
    """
    keyring-based implementation of username/password query

    Passwords are saved in gnome keyring, OSX/Chain or other platform
    specific storage and keyed by the repository url
    """
    # Calculate the true remote url. authuri happens to contain things like
    # https://repo.machine.com/repos/apps/module?pairs=0000000000000000000000000000000000000000-0000000000000000000000000000000000000000&cmd=between
    parsed_url = urlparse(authuri)
    base_url = "%s://%s%s" % (parsed_url.scheme, parsed_url.netloc, parsed_url.path)

    # Extracting possible username/password stored in directly in repository url
    user, pwd = urllib2.HTTPPasswordMgrWithDefaultRealm.find_user_password(self, realm, authuri)

    # Checking the local cache (single command may repeat the call many
    # times)
    if not hasattr(self, '_pwd_cache'):
       self._pwd_cache = {}
    cache_key = (realm, base_url)
    cached_auth = self._pwd_cache.get(cache_key)
    if cached_auth:
       return cached_auth

    # Loading username (and maybe password) from [auth] in local .hg/hgrc
    if not user:
       # Lines below unfortunately do not work, readauthtoken
       # always return None. Why? Because
       # self.ui here describes the *remote* repository, so 
       # does *not* contain any option from local .hg/hgrc. 
       #
       #auth_token = self.readauthtoken(base_url)
       #if auth_token:
       #   user, pwd = auth.get('username'), auth.get('password')
       #
       # so - workaround
       repo_root = self.ui.config("bundle", "mainreporoot")
       if repo_root:
          from mercurial.ui import ui as _ui
          import os
          local_ui = _ui(self.ui)
          local_ui.readconfig(os.path.join(repo_root, ".hg", "hgrc"))
          local_passwordmgr = passwordmgr(local_ui)
          auth_token = local_passwordmgr.readauthtoken(base_url)
          if auth_token:
             user, pwd = auth.get('username'), auth.get('password')



    
    user, pwd = password_store.get_password(base_url)
    if user and pwd:
       return user, pwd

    if not self.ui.interactive():
       raise util.Abort(_('mercurial_keyring: http authorization required'))
    self.ui.write(_("http authorization required\n"))
    self.ui.status(_("realm: %s, url: %s\n" % (realm, base_url)))
    user = self.ui.prompt(_("user:"), default = user)
    pwd = self.ui.getpass(_("password: "))

    password_store.save_password(base_url, user, pwd)

    return user, pwd
    #return None, None

