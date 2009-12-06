# -*- coding: utf-8 -*-
#
# mercurial_keyring: save passwords in password database
#
# Copyright 2009 Marcin Kasperski <Marcin.Kasperski@mekk.waw.pl>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

"""
=================
mercurial_keyring
=================

Mercurial extension to securely save HTTP and SMTP authentication
passwords in password databases (Gnome Keyring, KDE KWallet,
OSXKeyChain, specific solutions for Win32 and command line). Uses and
wraps services of the keyring_ library.

.. _keyring: http://pypi.python.org/pypi/keyring

How does it work
================

The extension prompts for the password on the first pull/push (in case
of HTTP) or first email (in case of SMTP), just like it is done by
default, but saves the given password (keyed by the combination of
username and remote repository url - for HTTP - or smtp server
address - for SMTP) in the password database. On successive runs it
checks for the username in ``.hg/hgrc``, then for suitable password in the
password database, and uses those credentials if found.

In case password turns out to be incorrect (either because it was
invalid, or because it was changed on the server) it just prompts the
user again.

Installation
============

Install keyring library:

::

    easy_install keyring

(or ``pip keyring``). On Debian "Sid" the library can be also
installed from the official archive (packages ``python-keyring``,
``python-keyring-gnome`` and ``python-keyring-kwallet``).

Then use one of the three options:

a) download ``mercurial_keyring.py``, save it anywhere you like and
put the following in ``~/.hgrc`` (or ``/etc/mercurial/hgrc``):

::

    [extensions]
    hgext.mercurial_keyring = /path/to/mercurial_keyring.py

b) save ``mercurial_keyring.py`` to ``mercurial/hgext`` directory and
use

::

    [extensions]
    hgext.mercurial_keyring = 

c) install ``mercurial_keyring`` using ``easy_install``:

::

    easy_install mercurial_keyring

and then configure ``~/.hgrc`` so:

::

    [extensions]
    mercurial_keyring = 

Password backend configuration
==============================

The library should usually pick the most appropriate password backend
without configuration. Still, if necessary, it can be configured using
``~/keyringrc.cfg`` file (``keyringrc.cfg`` in the home directory of
the current user). Refer to keyring_ docs for more details.

''I considered handling similar options in hgrc, but decided that
single user may use more than one keyring-based script. Still, I am
open to suggestions.''

Repository configuration (HTTP)
===============================

Edit repository-local ``.hg/hgrc`` and save there the remote
repository path and the username, but do not save the password. For
example:

::

    [paths]
    myremote = https://my.server.com/hgrepo/someproject

    [auth]
    myremote.schemes = http https
    myremote.prefix = my.server.com/hgrepo
    myremote.username = mekk

Simpler form with url-embedded name can also be used:

::

    [paths]
    bitbucket = https://User@bitbucket.org/User/project_name/

Note: if both username and password are given in ``.hg/hgrc``,
extension will use them without using the password database. If
username is not given, extension will prompt for credentials every
time, also without saving the password.

Repository configuration (SMTP)
===============================

Edit either repository-local ``.hg/hgrc``, or ``~/.hgrc`` and set
there all standard email and smtp properties, including smtp
username, but without smtp password. For example:

::

    [email]
    method = smtp
    from = Joe Doe <Joe.Doe@remote.com>

    [smtp]
    host = smtp.gmail.com
    port = 587
    username = JoeDoe@gmail.com
    tls = true

Just as in case of HTTP, you *must* set username, but *must not* set
password here to use the extension, in other cases it will revert to
the default behaviour.

Usage
=====

Configure the repository as above, then just pull, push, etc.
You should be asked for the password only once (per every
username+remote_repository_url combination).

Similarly, for email, configure as above and just email.
Again, you will be asked for the password once (per every
username+email_server_name+email_server_port).

Implementation details
======================

The extension is monkey-patching the mercurial passwordmgr class to
replace the find_user_password method. Detailed order of operations
is described in the comments inside the code.

Development
===========

Development is tracked on http://bitbucket.org/Mekk/mercurial_keyring/

"""

from mercurial import hg, repo, util
from mercurial.i18n import _
try:
    from mercurial.url import passwordmgr
except:
    from mercurial.httprepo import passwordmgr
from mercurial.httprepo import httprepository
from mercurial import mail

import keyring
from urlparse import urlparse
import urllib2
import smtplib, socket

KEYRING_SERVICE = "Mercurial"

############################################################

def monkeypatch_method(cls):
    def decorator(func):
        setattr(cls, func.__name__, func)
        return func
    return decorator

############################################################

class PasswordStore(object):
    """
    Helper object handling keyring usage (password save&restore,
    the way passwords are keyed in the keyring).
    """
    def __init__(self):
        self.cache = dict()
    def get_http_password(self, url, username):
        return keyring.get_password(KEYRING_SERVICE,
                                    self._format_http_key(url, username))
    def set_http_password(self, url, username, password):
        keyring.set_password(KEYRING_SERVICE,
                             self._format_http_key(url, username),
                             password)
    def clear_http_password(self, url, username):
        self.set_http_password(url, username, "")
    def _format_http_key(self, url, username):
        return "%s@@%s" % (username, url)
    def get_smtp_password(self, machine, port, username):
        return keyring.get_password(
            KEYRING_SERVICE,
            self._format_smtp_key(machine, port, username))
    def set_smtp_password(self, machine, port, username, password):
        keyring.set_password(
            KEYRING_SERVICE,
            self._format_smtp_key(machine, port, username),
            password)
    def clear_smtp_password(self, machine, port, username):
        self.set_smtp_password(url, username, "")
    def _format_smtp_key(self, machine, port, username):
        return "%s@@%s:%s" % (username, machine, str(port))

password_store = PasswordStore()

############################################################

class HTTPPasswordHandler(object):
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
        Actual implementation of find_user_password - different
        ways of obtaining the username and password.
        """
        ui = pwmgr.ui

        # If we are called again just after identical previous
        # request, then the previously returned auth must have been
        # wrong. So we note this to force password prompt (and avoid
        # reusing bad password indifinitely).
        after_bad_auth = (self.last_reply \
                          and (self.last_reply['realm'] == realm) \
                          and (self.last_reply['authuri'] == authuri))
           
        # Strip arguments to get actual remote repository url.
        base_url = self.canonical_url(authuri)

        # Extracting possible username (or password)
        # stored directly in repository url
        user, pwd = urllib2.HTTPPasswordMgrWithDefaultRealm.find_user_password(
            pwmgr, realm, authuri)
        if user and pwd:
            self._debug_reply(ui, _("Auth data found in repository URL"), 
                              base_url, user, pwd)
            self.last_reply = dict(realm=realm,authuri=authuri,user=user)
            return user, pwd

        # Checking the memory cache (there may be many http calls per command)
        cache_key = (realm, base_url)
        if not after_bad_auth:
            cached_auth = self.pwd_cache.get(cache_key)
            if cached_auth:
                user, pwd = cached_auth
                self._debug_reply(ui, _("Cached auth data found"), 
                                  base_url, user, pwd)
                self.last_reply = dict(realm=realm,authuri=authuri,user=user)
                return user, pwd

        # Loading username and maybe password from [auth] in .hg/hgrc
        nuser, pwd = self.load_hgrc_auth(ui, base_url)
        if nuser:
            if user:
                raise util.Abort(_('mercurial_keyring: username for %s specified both in repository path (%s) and in .hg/hgrc/[auth] (%s). Please, leave only one of those' % (base_url, user, nuser)))
            user = nuser
            if pwd:
                self.pwd_cache[cache_key] = user, pwd
                self._debug_reply(ui, _("Auth data set in .hg/hgrc"), 
                                  base_url, user, pwd)
                self.last_reply = dict(realm=realm,authuri=authuri,user=user)
                return user, pwd
            else:
                ui.debug(_("Username found in .hg/hgrc: %s\n" % user))

        # Loading password from keyring. 
        # Only if username is known (so we know the key) and we are
        # not after failure (so we don't reuse the bad password).
        if user and not after_bad_auth:
            pwd = password_store.get_http_password(base_url, user)
            if pwd:
                self.pwd_cache[cache_key] = user, pwd
                self._debug_reply(ui, _("Keyring password found"), 
                                  base_url, user, pwd)
                self.last_reply = dict(realm=realm,authuri=authuri,user=user)
                return user, pwd
        
        # Is the username permanently set?
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
            # Saving password to the keyring.
            # It is done only if username is permanently set.
            # Otherwise we won't be able to find the password so it
            # does not make much sense to preserve it
            ui.debug("Saving password for %s to keyring\n" % user)
            password_store.set_http_password(base_url, user, pwd)

        # Saving password to the memory cache
        self.pwd_cache[cache_key] = user, pwd

        self._debug_reply(ui, _("Manually entered password"), 
                          base_url, user, pwd)
        self.last_reply = dict(realm=realm,authuri=authuri,user=user)
        return user, pwd

    def load_hgrc_auth(self, ui, base_url):
        """
        Loading username and possibly password from [auth] in local
        repo .hgrc
        """
        # Theoretically 3 lines below should do:
        
        #auth_token = self.readauthtoken(base_url)
        #if auth_token:
        #   user, pwd = auth.get('username'), auth.get('password')
        
        # Unfortunately they do not work, readauthtoken always return
        # None. Why? Because ui (self.ui of passwordmgr) describes the
        # *remote* repository, so does *not* contain any option from
        # local .hg/hgrc.

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
        Strips query params from url. Used to convert urls like
        https://repo.machine.com/repos/apps/module?pairs=0000000000000000000000000000000000000000-0000000000000000000000000000000000000000&cmd=between
        to
        https://repo.machine.com/repos/apps/module
        """
        parsed_url = urlparse(authuri)
        return "%s://%s%s" % (parsed_url.scheme, parsed_url.netloc,
                              parsed_url.path)

    def _debug_reply(self, ui, msg, url, user, pwd):
        ui.debug("%s. Url: %s, user: %s, passwd: %s\n" % (
            msg, url, user, pwd and '*' * len(pwd) or 'not set'))

############################################################

@monkeypatch_method(passwordmgr)
def find_user_password(self, realm, authuri):
    """
    keyring-based implementation of username/password query
    for HTTP(S) connections

    Passwords are saved in gnome keyring, OSX/Chain or other platform
    specific storage and keyed by the repository url
    """
    # Extend object attributes
    if not hasattr(self, '_pwd_handler'):
        self._pwd_handler = HTTPPasswordHandler()

    return self._pwd_handler.find_auth(self, realm, authuri)

############################################################

def try_smtp_login(ui, smtp_obj, username, password):
    """
    Attempts smtp login on smtp_obj (smtplib.SMTP) using username and
    password. 

    Returns:
    - True if login succeeded
    - False if login failed due to the wrong credentials

    Throws Abort exception if login failed for any other reason.

    Immediately returns False if password is empty
    """
    if not password:
        return False
    try:
        ui.note(_('(authenticating to mail server as %s)\n') %
                 (username))
        smtp_obj.login(username, password)
        return True
    except smtplib.SMTPException, inst:
        if inst.smtp_code == 535:
            ui.status(_("SMTP login failed: %s\n\n") % inst.smtp_error)
            return False
        else:
            raise util.Abort(inst)

def keyring_supported_smtp(ui, username):
    """
    keyring-integrated replacement for mercurial.mail._smtp
    Used only when configuration file contains username, but
    does not contain the password.

    Most of the routine below is copied as-is from
    mercurial.mail._smtp. The only changed part is
    marked with #>>>>> and #<<<<< markers
    """
    local_hostname = ui.config('smtp', 'local_hostname')
    s = smtplib.SMTP(local_hostname=local_hostname)
    mailhost = ui.config('smtp', 'host')
    if not mailhost:
        raise util.Abort(_('no [smtp]host in hgrc - cannot send mail'))
    mailport = int(ui.config('smtp', 'port', 25))
    ui.note(_('sending mail: smtp host %s, port %s\n') %
            (mailhost, mailport))
    s.connect(host=mailhost, port=mailport)
    if ui.configbool('smtp', 'tls'):
        if not hasattr(socket, 'ssl'):
            raise util.Abort(_("can't use TLS: Python SSL support "
                               "not installed"))
        ui.note(_('(using tls)\n'))
        s.ehlo()
        s.starttls()
        s.ehlo()
        
    #>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    stored = password = password_store.get_smtp_password(
        mailhost, mailport, username)
    # No need to check whether password was found as try_smtp_login
    # just returns False if it is absent.
    while not try_smtp_login(ui, s, username, password):
        password = ui.getpass(_("Password for %s on %s:%d: ") % (username, mailhost, mailport))

    if stored != password:
        password_store.set_smtp_password(
            mailhost, mailport, username, password)
    #<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

    def send(sender, recipients, msg):
        try:
            return s.sendmail(sender, recipients, msg)
        except smtplib.SMTPRecipientsRefused, inst:
            recipients = [r[1] for r in inst.recipients.values()]
            raise util.Abort('\n' + '\n'.join(recipients))
        except smtplib.SMTPException, inst:
            raise util.Abort(inst)

    return send

############################################################

orig_smtp = mail._smtp

@monkeypatch_method(mail)
def _smtp(ui):
    """
    build an smtp connection and return a function to send email

    This is the monkeypatched version of _smtp(ui) function from
    mercurial/mail.py. It calls the original unless username
    without password is given in the configuration.
    """
    username = ui.config('smtp', 'username')
    password = ui.config('smtp', 'password')

    if username and not password:
        return keyring_supported_smtp(ui, username)
    else:
        return orig_smtp(ui)
