try:
	from setuptools import setup, find_packages
except ImportError:
	from ez_setup import use_setuptools
	use_setuptools()
	from setuptools import setup, find_packages

setup(
	name = "mercurial_keyring",
	version = '0.3.1',
	author = 'Marcin Kasperski',
	author_email = 'Marcin.Kasperski@mekk.waw.pl',
	url = 'http://mekk.waw.pl',
	description = 'Mercurial Keyring Extension',
	long_description = '''mercurial_keyring preserves passwords via keyring (http://pypi.python.org/pypi/keyring) library, using OSX/Keychain, KDE KWallet, Gnome Keyring, or internally supported storage (also on Win32).''',
	license = 'BSD',
	py_modules = ['mercurial_keyring'],
	keywords = "mercurial hg keyring password",
	classifiers = [
		'Development Status :: 4 - Beta',
		'Environment :: Console',
		'Intended Audience :: Developers',
		'License :: OSI Approved :: BSD License',
		'Operating System :: OS Independent',
		'Topic :: Software Development :: Libraries',
		'Topic :: Software Development :: Libraries :: Python Modules',
		'Topic :: Software Development :: Version Control'
		],
	install_requires = ['keyring'],
	zip_safe = True,
	)
