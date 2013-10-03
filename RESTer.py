import json
import re

import sublime
import sublime_plugin

try:
    # Sublime Text 3
    from RESTer.common.overrideable import OverrideableSettings
    from RESTer.core import message
    from RESTer.core import constants
    from RESTer.core import util
    from RESTer.core.parse import RequestParser
    ST3 = True
    ST2 = False
except ImportError:
    # Sublime Text 2
    from common.overrideable import OverrideableSettings
    from core import message
    from core import constants
    from core import util
    from core.parse import RequestParser
    ST3 = False
    ST2 = True


class ResterHttpRequestCommand(sublime_plugin.WindowCommand):

    def run(self):

        # Store references.
        self.request_view = self.window.active_view()
        self.eol = util.get_end_of_line_character(self.request_view)
        self.settings = self._get_settings()

        # Perform commands on the request.
        # Store the number of changes made so we can undo them.
        try:
            changes = self.request_view.change_count()
            self._run_request_commands()
            changes = self.request_view.change_count() - changes
        except:
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

        # Determine the encoding of the editor starting the request.
        # Sublime returns "Undefined" for views that are not yet saved.
        encoding = self.request_view.encoding()
        if not encoding or encoding == "Undefined":
            encoding = "UTF-8"

        request_parser = RequestParser(self.settings, self.eol)
        rqst = request_parser.get_request(text, encoding)
        print("Method:", rqst.method)
        print("Host:", rqst.host)
        print("Path:", rqst.path)
        print("Headers:", rqst.headers)
        print("Body:", rqst.body)

    def _get_selection(self):
        # Return the selected text or the entire buffer.
        view = self.request_view
        sels = view.sel()
        if len(sels) == 1 and sels[0].empty():
            # No selection. Use the entire buffer.
            selection = view.substr(sublime.Region(0, view.size()))
        else:
            # Concatenate the selections into one large string.
            selection = ""
            for sel in sels:
                selection += view.substr(sel)
        return selection

    def _get_settings(self):

        # Scan the request for overrides.
        text = self._get_selection().lstrip()
        text = util.normalize_line_endings(text, self.eol)

        headers = text.split(self.eol * 2, 1)[0]

        # Build a dictionary of the overrides.
        overrides = {}
        for (name, value) in re.findall(constants.RE_OVERRIDE, headers, re.MULTILINE):
            try:
                overrides[name] = json.loads(value)
            except ValueError:
                # If unable to parse as JSON, assume it's an un-quoted string.
                overrides[name] = value

        # Return an OverrideableSettings object.
        return OverrideableSettings(
            settings=sublime.load_settings(constants.SETTINGS_FILE),
            overrides=overrides)

    def _normalize_command(self, command):

        # Return a well formed dictionary for a request or response command
        valid = False
        string_class = str
        if ST2:
            string_class = basestring

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

    def _run_request_commands(self):
        view = self.request_view
        commands = self.settings.get("request_commands", [])
        for command in commands:
            command = self._normalize_command(command)
            if command:
                view.run_command(command["name"], command["args"])
