"""
Sublime imports modules in package roots, but will not look deeper.
This module manually reloads the package's modules in such an order that
modules with dependencies are loaded after their dependencies.
"""

import sys
import sublime

MODULE_PREFIX = "rester"
PACKAGE_DIRECTORY = "rester-sublime-http-client"

ST_VERSION = 2
if int(sublime.version()) > 3000:
    ST_VERSION = 3

if ST_VERSION == 3:
    from imp import reload

mod_prefix = MODULE_PREFIX
if ST_VERSION == 3:
    mod_prefix = PACKAGE_DIRECTORY + "." + mod_prefix

# Reload modules in this order.
# Modules with dependencies must be loaded after the dependencies.
mods_load_order = [
    '.overrideable',
    '.util',
    '.message',
    '.http',
    '.parse',
    '.commands.auto_form_encode_command',
    '.commands.http_request_command',
    '.commands',
]

for suffix in mods_load_order:
    mod = mod_prefix + suffix
    if mod in sys.modules:
        reload(sys.modules[mod])
