import json
import re

from ..overrideable import OverrideableSettings
from ..parse import RequestParser
from ..util import get_end_of_line_character
from ..util import normalize_line_endings
import sublime
import sublime_plugin


MAX_REDIRECTS = 10
RE_OVERRIDE = """^\s*@\s*([^\:]*)\s*:\s*(.*)$"""
SETTINGS_FILE = "RESTer.sublime-settings"


class ResterHttpRequestCommand(sublime_plugin.WindowCommand):
    def __init__(self, *args, **kwargs):

        self.encoding = "UTF-8"
        self.eol = "\n"
        self.request_view = None
        self.settings = None
        self._redirect_count = 0
        self._requesting = False
        self._completed_message = "Done"
        sublime_plugin.WindowCommand.__init__(self, *args, **kwargs)

    def run(self):

        print("RESTer")

        # Store references.
        self.request_view = self.window.active_view()
        self.eol = get_end_of_line_character(self.request_view)
        self.settings = self._get_settings()
        self._completed_message = "Done."
        self._redirect_count = 0
        self._requesting = False

        # Determine the encoding of the editor starting the request.
        # Sublime returns "Undefined" for views that are not yet saved.
        self.encoding = self.request_view.encoding()
        if not self.encoding or self.encoding == "Undefined":
            self.encoding = "UTF-8"

        # Perform commands on the request buffer.
        # Store the number of changes made so we can undo them.
        try:
            changes = self.request_view.change_count()
            self._run_request_commands()
            changes = self.request_view.change_count() - changes
        except AttributeError:
            # ST2 does not have a change_count() method.
            # It does allow creating an Edit on the fly though.
            edit = self.request_view.begin_edit()
            self._run_request_commands()
            self.request_view.end_edit(edit)
            changes = 1

        # Read the selected text.
        text = self._get_selection()

        # Undo the request commands to return to the starting state.
        for i in range(changes):
            self.request_view.run_command("undo")

        # Build a message.Request from the text.
        request_parser = RequestParser(self.settings, self.eol)
        request = request_parser.get_request(text)
        print(request)

    def _get_selection(self):
        # Return a string of the selected text or the entire buffer.
        # if there are multiple selections, concatenate them.
        view = self.request_view
        sels = view.sel()
        if len(sels) == 1 and sels[0].empty():
            selection = view.substr(sublime.Region(0, view.size()))
        else:
            selection = ""
            for sel in sels:
                selection += view.substr(sel)
        return selection

    def _get_settings(self):

        # Return a setting-like object that combines the user's settings with
        # overrides from the current request.

        # Scan the request for overrides.
        text = self._get_selection().lstrip()
        text = normalize_line_endings(text, self.eol)

        headers = text.split(self.eol * 2, 1)[0]

        # Build a dictionary of the overrides.
        overrides = {}
        for (name, value) in re.findall(RE_OVERRIDE, headers, re.MULTILINE):
            try:
                overrides[name] = json.loads(value)
            except ValueError:
                # If unable to parse as JSON, assume it's an un-quoted string.
                overrides[name] = value

        # Return an OverrideableSettings object.
        return OverrideableSettings(
            settings=sublime.load_settings(SETTINGS_FILE),
            overrides=overrides)

    def _run_request_commands(self):
        # Process the request buffer to prepare the contents for the request.
        view = self.request_view
        commands = self.settings.get("request_commands", [])
        for command in commands:
            command = ResterHttpRequestCommand.normalize_command(command)
            if command:
                view.run_command(command["name"], command["args"])

    @staticmethod
    def normalize_command(command):

        # Return a well formed dictionary for a request or response command

        valid = False

        # Find the stirng class. (str for py3, basestring for py2)
        string_class = str
        try:
            # If Python 2, use basestring instead of str
            #noinspection PyStatementEffect
            basestring
            string_class = basestring
        except NameError:
            pass

        if isinstance(command, string_class):
            command = {"name": command}
            valid = True
        elif isinstance(command, dict):
            if "name" in command:
                valid = True

        # Skip here if invalid.
        if not valid:
            print("Skipping invalid command.")
            print("Each command must be a string or a dict with a 'name'")
            print(command)
            return None

        # Ensure each command has all needed fields.
        if not "args" in command:
            command["args"] = None

        return command
