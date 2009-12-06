; -*- mode: rst -*-

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

Additional notes
================

Information about this extension is also available
on Mercurial Wiki: http://mercurial.selenic.com/wiki/KeyringExtension