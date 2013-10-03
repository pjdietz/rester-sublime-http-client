import json
import re

import sublime
import sublime_plugin

try:
    # Sublime Text 3
    from RESTer.common.overrideable import OverrideableSettings
    from RESTer.core import http
    from RESTer.core import parse
    from RESTer.core import util
    from RESTer.core.parse import RequestParser
except ImportError:
    # Sublime Text 2
    from common.overrideable import OverrideableSettings
    from core import http
    from core import parse
    from core import util
    from core.parse import RequestParser


RE_OVERRIDE = """^\s*@\s*([^\:]*)\s*:\s*(.*)$"""
SETTINGS_FILE = "RESTer.sublime-settings"


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
        request = request_parser.get_request(text, encoding)

        # Create, start, and handle a thread for the selection.
        thread = http.HttpRequestThread(request, self.settings, encoding)
        thread.start()
        self._handle_thread(thread)

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

    def _handle_thread(self, thread, i=0, dir=1):

        if thread.is_alive():
            # This animates a little activity indicator in the status area.
            before = i % 8
            after = 7 - before
            if not after:
                dir = -1
            if not before:
                dir = 1
            i += dir
            message = "RESTer [%s=%s]" % (" " * before, " " * after)
            self.request_view.set_status("rester", message)
            sublime.set_timeout(lambda:
                                self._handle_thread(thread, i, dir), 100)

        elif thread.success:
            # Success.
            self._complete_thread(thread)

        else:
            # Failed.
            self.request_view.erase_status("rester")
            if thread.message:
                sublime.status_message(thread.message)
            else:
                sublime.status_message("Unable to make request.")

    def _complete_thread(self, thread):

        response_parser = parse.ResponseParser(self.settings, self.eol)
        response = response_parser.get_response(thread.response, thread.body)

        print(response)





    def _normalize_command(self, command):

        # Return a well formed dictionary for a request or response command
        valid = False

        # Find the stirng class. (str for py3, basestring for py2)
        string_class = str
        try:
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

    def _run_request_commands(self):
        view = self.request_view
        commands = self.settings.get("request_commands", [])
        for command in commands:
            command = self._normalize_command(command)
            if command:
                view.run_command(command["name"], command["args"])
