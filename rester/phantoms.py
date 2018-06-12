import sublime
import sublime_plugin

from .constants import SYNTAX_FILE


class RESTer(sublime_plugin.ViewEventListener):
    def __init__(self, view):
        self.view = view
        self.phantom_set = sublime.PhantomSet(view)
        self.timeout_scheduled = False
        self.needs_update = False

    @classmethod
    def is_applicable(cls, settings):
        syntax = settings.get('syntax')
        return syntax == SYNTAX_FILE

    def update_phantoms(self):
        phantoms = []

        # Don't do any calculations on 1MB or larger files
        if self.view.size() < 2**20:
            candidates = self.view.find_all(r'\n(https?://|[A-Z]+ )')
            for r in candidates:
                phantoms.append(sublime.Phantom(
                    sublime.Region(r.a),
                    '<style>a{color:#999}</style><small><a href="%s">Send Request</a></small>&nbsp;' % (r.a + 1),
                    sublime.LAYOUT_BLOCK,
                    self.rester_http_request))

        self.phantom_set.update(phantoms)

    def rester_http_request(self, href):
        self.view.window().run_command('rester_http_request', {'pos': int(href)})

    def handle_timeout(self):
        self.timeout_scheduled = False
        if self.needs_update:
            self.needs_update = False
            self.update_phantoms()

    def on_activated(self):
        self.update_phantoms()

    def on_modified(self):
        # Call update_phantoms(), but not any more than 10 times a second
        if self.timeout_scheduled:
            self.needs_update = True
        else:
            self.timeout_scheduled = True
            sublime.set_timeout(lambda: self.handle_timeout(), 100)
            self.update_phantoms()
