"""
Sublime imports modules it finds in package roots, but will not look deeper.
This module loads the modules needed for the package and manages reloading
of these dependencies when this module is itself reloaded.
"""

import sys
import sublime

PACKAGE_DIRECTORY = "rester-sublime-http-client"
RELOADER_NAME = "rester.reloader"

ST_VERSION = 2
if int(sublime.version()) > 3000:
    ST_VERSION = 3


# Reload modules.
reloader_name = RELOADER_NAME
if ST_VERSION == 3:
    reloader_name = PACKAGE_DIRECTORY + "." + reloader_name
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
