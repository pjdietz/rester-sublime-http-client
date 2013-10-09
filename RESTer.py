"""
Sublime imports modules it finds in package roots, but will not look deeper.
This module loads the modules needed for the package and manages reloading
of these dependencies when this module is itself reloaded.
"""

import os
import sys

import sublime

EXPECTED_PACKAGE_DIR = "rester-sublime-http-client"
RELOADER_NAME = "rester.reloader"

if int(sublime.version()) > 3000:
    ST_VERSION = 3
    PACKAGE_DIR = __name__.split('.')[0]
else:
    ST_VERSION = 2
    PACKAGE_DIR = os.path.basename(os.getcwd())

# Ensure the package is installed in the correct directory.
# The menu commands will not work properly otherwise.
if PACKAGE_DIR != EXPECTED_PACKAGE_DIR:
    m = u'RESTer appears to be installed incorrectly.\n\n' \
        u'It should be installed as "%s", but is installed as "%s".\n\n'
    message = m % (EXPECTED_PACKAGE_DIR, PACKAGE_DIR)
    # If installed unpacked
    if os.path.exists(os.path.join(sublime.packages_path(), PACKAGE_DIR)):
        m = u'Please use the Preferences > Browse Packages... menu ' \
            u'entry to open the "Packages/" folder and rename "%s" to "%s" '
        message += m % (PACKAGE_DIR, EXPECTED_PACKAGE_DIR)
    # If installed as a .sublime-package file
    else:
        m = u'Please use the Preferences > Browse Packages... menu ' \
            u'entry to open the "Packages/" folder, then browse up a ' \
            u'folder and into the "Installed Packages/" folder.\n\n' \
            u'Inside of "Installed Packages/", rename ' \
            u'"%s.sublime-package" to "%s.sublime-package" '
        message += m % (PACKAGE_DIR, EXPECTED_PACKAGE_DIR)
    message += u"and restart Sublime Text."
    sublime.error_message(message)

# Reload modules.
reloader_name = RELOADER_NAME
if ST_VERSION == 3:
    reloader_name = PACKAGE_DIR + "." + reloader_name
    from imp import reload
if reloader_name in sys.modules:
    reload(sys.modules[reloader_name])

# Initial loading.
try:
    # Python 3
    from .rester import reloader
    from .rester.commands import *
except ValueError:
    # Python 2
    from rester import reloader
    from rester.commands import *
