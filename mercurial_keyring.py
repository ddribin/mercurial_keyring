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
    # Calculate the true url. authuri happens to contain things like
    # https://repo.machine.com/repos/apps/module?pairs=0000000000000000000000000000000000000000-0000000000000000000000000000000000000000&cmd=between
    parsed_url = urlparse(authuri)
    base_url = "%s://%s%s" % (parsed_url.scheme, parsed_url.netloc, parsed_url.path)

    #from mercurial import commands, hg
    #commands.showconfig(self.ui, hg.repository(self.ui, '.'))

    for section, name, value in self.ui.walkconfig():
            print "cfg", section, name, value

    # Extracting possible username/password stored in repository url
    user, pwd = urllib2.HTTPPasswordMgrWithDefaultRealm.find_user_password(self, realm, authuri)

    auth_token = self.readauthtoken(base_url)
    print "token", auth_token
    print "configitems", list(self.ui.configitems('auth'))
    print "configitems", list(self.ui.configitems('auth', untrusted=True))
    print "configitems", list(self.ui.configitems('paths'))
    print self.ui

    print "find_user_password", realm, base_url, user, pwd, auth_token
    
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

