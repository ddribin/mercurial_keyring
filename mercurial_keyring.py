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
from mercurial.httprepo import httprepository

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
    Helper object handling keyring usage (password save&restore).
    """
    def __init__(self):
        self.cache = dict()
    def get_password(self, url, username):
        return keyring.get_password(KEYRING_SERVICE,
                                    self._format_key(url, username))
    def set_password(self, url, username, password):
        keyring.set_password(KEYRING_SERVICE,
                             self._format_key(url, username),
                             password)
    def clear_password(self, url, username):
        self.set_password(url, username, "")
    def _format_key(self, url, username):
        return "%s@@%s" % (username, url)

password_store = PasswordStore()

############################################################

class PasswordHandler(object):
    """
    Actual implementation of password handling (user prompting,
    configuration file searching, keyring save&restore).

    Object of this class is bound as passwordmgr attribute.
    """
    def __init__(self):
        self.pwd_cache = {}
        self.last_reply = None

    def find_auth(self, pwmgr, realm, authuri):
        """
        Actual implementation of find_user_password
        """
        ui = pwmgr.ui

        # If we are called again just after identical previous request,
        # then the previously returned auth must have been wrong. So we
        # note this to force password prompt
        after_bad_auth = (self.last_reply \
           and (self.last_reply['realm'] == realm) \
           and (self.last_reply['authuri'] == authuri))
           
        base_url = self.canonical_url(authuri)

        # Extracting possible username (or password)
        # stored in directly in repository url
        user, pwd = urllib2.HTTPPasswordMgrWithDefaultRealm.find_user_password(pwmgr, realm, authuri)
        if user and pwd:
           self._debug_reply(ui, _("Auth data found in repository URL"), base_url, user, pwd)
           self.last_reply = dict(realm=realm,authuri=authuri,user=user)
           return user, pwd

        # Checking the memory cache (there may be many http calls per command)
        cache_key = (realm, base_url)
        if not after_bad_auth:
           cached_auth = self.pwd_cache.get(cache_key)
           if cached_auth:
              user, pwd = cached_auth
              self._debug_reply(ui, _("Cached auth data found"), base_url, user, pwd)
              self.last_reply = dict(realm=realm,authuri=authuri,user=user)
              return user, pwd

        # Loading username and maybe password from [auth]
        nuser, pwd = self.load_hgrc_auth(ui, base_url)
        if nuser:
           if user:
              raise util.Abort(_('mercurial_keyring: username for %s specified both in repository path (%s) and in .hg/hgrc/[auth] (%s). Please, leave only one of those' % (base_url, user, nuser)))
           user = nuser
           if pwd:
              self.pwd_cache[cache_key] = user, pwd
              self._debug_reply(ui, _("Auth data set in .hg/hgrc"), base_url, user, pwd)
              self.last_reply = dict(realm=realm,authuri=authuri,user=user)
              return user, pwd
           else:
              ui.debug(_("Username found in .hg/hgrc: %s\n" % user))

        # If username is known, and we are not after failure, we can try keyring
        if user and not after_bad_auth:
           pwd = password_store.get_password(base_url, user)
           if pwd:
              self.pwd_cache[cache_key] = user, pwd
              self._debug_reply(ui, _("Keyring password found"), base_url, user, pwd)
              self.last_reply = dict(realm=realm,authuri=authuri,user=user)
              return user, pwd
        
        fixed_user = (user and True or False)

        # Last resort: interactive prompt
        if not ui.interactive():
           raise util.Abort(_('mercurial_keyring: http authorization required'))
        ui.write(_("http authorization required\n"))
        ui.status(_("realm: %s\n") % realm)
        if fixed_user:
           ui.write(_("user: %s (fixed in .hg/hgrc)\n" % user))
        else:
           user = ui.prompt(_("user:"), default=None)
        pwd = ui.getpass(_("password: "))

        if fixed_user:
           # We save in keyring only if username is fixed. Otherwise we won't
           # be able to find the password so it does not make any sense to 
           # preserve it
           ui.debug("Saving password for %s to keyring\n" % user)
           password_store.set_password(base_url, user, pwd)

        self.pwd_cache[cache_key] = user, pwd
        self._debug_reply(ui, _("Manually entered password"), base_url, user, pwd)
        self.last_reply = dict(realm=realm,authuri=authuri,user=user)
        return user, pwd

    def load_hgrc_auth(self, ui, base_url):
        """
        Loading username and possibly password from [auth] in local
        repo .hgrc
        """
        # Lines below unfortunately do not work, readauthtoken
        # always return None. Why? Because
        # ui (self.ui of passwordmgr)  describes the *remote* repository, so 
        # does *not* contain any option from local .hg/hgrc. 

        #auth_token = self.readauthtoken(base_url)
        #if auth_token:
        #   user, pwd = auth.get('username'), auth.get('password')
     
        # Workaround: we recreate the repository object
        repo_root = ui.config("bundle", "mainreporoot")
        if repo_root:
           from mercurial.ui import ui as _ui
           import os
           local_ui = _ui(ui)
           local_ui.readconfig(os.path.join(repo_root, ".hg", "hgrc"))
           local_passwordmgr = passwordmgr(local_ui)
           auth_token = local_passwordmgr.readauthtoken(base_url)
           if auth_token:
              return auth_token.get('username'), auth_token.get('password')
        return None, None


    def canonical_url(self, authuri):
        """
        Strips query params from url. Used to convert
        https://repo.machine.com/repos/apps/module?pairs=0000000000000000000000000000000000000000-0000000000000000000000000000000000000000&cmd=between
        to
        https://repo.machine.com/repos/apps/module
        """
        parsed_url = urlparse(authuri)
        return "%s://%s%s" % (parsed_url.scheme, parsed_url.netloc, parsed_url.path)

    def _debug_reply(self, ui, msg, url, user, pwd):
        ui.debug("%s. Url: %s, user: %s, passwd: %s\n" % (msg, url, user, pwd and '*' * len(pwd) or 'not set'))

############################################################

# The idea: if we are re-asked with exactly the same params
# (authuri, not base_url) then password must have been wrong.

@monkeypatch_method(passwordmgr)
def find_user_password(self, realm, authuri):
    """
    keyring-based implementation of username/password query

    Passwords are saved in gnome keyring, OSX/Chain or other platform
    specific storage and keyed by the repository url
    """
    # Extend object attributes
    if not hasattr(self, '_pwd_handler'):
       self._pwd_handler = PasswordHandler()

    return self._pwd_handler.find_auth(self, realm, authuri)

