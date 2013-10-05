import json
import os
import re
import tempfile

import sublime
import sublime_plugin
from rester import util

try:
    # Sublime Text 3
    from RESTer.common.overrideable import OverrideableSettings
    from RESTer.core import http
    from RESTer.core import parse
    from RESTer.core import util
    from RESTer.core.message import Request
    from RESTer.core.parse import RequestParser
    from urllib.parse import parse_qs
    from urllib.parse import urljoin
    from urllib.parse import urlparse

except ImportError:
    # Sublime Text 2
    from rester.overrideable import OverrideableSettings
    from core import http
    from rester.message import Request
    from rester.parse import RequestParser
    from urlparse import parse_qs
    from urlparse import urlparse
    from urlparse import urljoin

MAX_REDIRECTS = 10
RE_OVERRIDE = """^\s*@\s*([^\:]*)\s*:\s*(.*)$"""
SETTINGS_FILE = "RESTer.sublime-settings"


class OldResterHttpRequestCommand(sublime_plugin.WindowCommand):

    def run(self):

        # Store references.
        self.request_view = self.window.active_view()
        self.eol = util.get_end_of_line_character(self.request_view)
        self.settings = self._get_settings()
        self.redirect_count = 0
        self._requesting = False
        self._completed_message = "Done."

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

        # Build a message.Request from the text.
        request_parser = RequestParser(self.settings, self.eol)
        request = request_parser.get_request(text, self.encoding)

        # Make the request.
        self._requesting = True
        self._check_if_requesting()
        self._start_request(request)

    def _complete(self, message):
        self._requesting = False
        self._completed_message = message

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

    def _start_request(self, request):

        # Output the request to the console.
        if self.settings.get("output_request", True):
            print("\n[Request]")
            print(request)

        # Create, start, and handle a thread for the selection.
        thread = http.HttpRequestThread(request, self.settings, self.encoding)
        thread.start()
        self._handle_thread(thread)

    def _check_if_requesting(self, i=0, dir=1):
        if self._requesting:
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
            sublime.set_timeout(lambda: self._check_if_requesting(i, dir), 100)
        else:
            if not self._completed_message:
                self._completed_message = "Done."
            self.request_view.set_status("rester", self._completed_message)

    def _handle_thread(self, thread):

        if thread.is_alive():
            # Working...
            sublime.set_timeout(lambda: self._handle_thread(thread), 100)

        elif thread.success:
            # Success.
            self._complete_thread(thread)

        else:
            # Failed.
            if thread.message:
                self._complete(thread.message)
            else:
                self._complete("Unable to make request.")

    def _complete_thread(self, thread):

        response = thread.response
        status_line = response.status_line

        # Output the response to the console.
        output_headers = self.settings.get("output_response_headers", True)
        output_body = self.settings.get("output_response_body", True)
        if output_headers or output_body:
            print("\n[Response]")
            if output_headers and output_body:
                print(response)
            elif output_headers:
                print(status_line)
                print("\n".join(response.headers))
            elif output_body:
                print(reponse.body)

        # Redirect.
        follow = self.settings.get("follow_redirects", True)
        follow_codes = self.settings.get("follow_redirect_status_codes", [])
        if follow and response.status in follow_codes:
            self._follow_redirect(response, thread.request)
            return

        # Stop now if the user does not want a response buffer.
        if not self.settings.get("response_buffer", True):
            self._complete("Request complete. " + status_line)
            return

        # Open a temporary file to write the response to.
        tmpfile = tempfile.NamedTemporaryFile("w", delete=False)

        # Body only, but only on success.
        success = 200 <= thread.response.status <= 299
        if success and self.settings.get("body_only", False):
            if response.body:
                tmpfile.write(body)
            body_only = True

        # Status line and headers. Store the file length.
        else:
            tmpfile.write(status_line + self.eol)
            tmpfile.write(self.eol.join(response.header_lines))
            if response.body:
                tmpfile.write(self.eol * 2)
                tmpfile.write(response.body)
            body_only = False

        # Close the file.
        tmpfile.close()
        filepath = tmpfile.name

        # Open the file in a new view.
        self.response_view = self.window.open_file(filepath, sublime.TRANSIENT)
        self._handle_response_view(tmpfile.name, status_line, body_only)

    def _follow_redirect(self, response, request):

        # Stop now in the event of an infinite loop.
        if self.redirect_count > MAX_REDIRECTS:
            self._complete("Maximum redirects reached.")
            return

        # Read the location header and start a new request.
        location = response.get_header("Location")

        # Stop now if no location header.
        if not location:
            self._complete("Unable to redirect. No Location header found.")
            return

        # Create a new request instance.
        redirect = Request()

        # Use GET unless the original request was HEAD.
        if request.method == "HEAD":
            redirect.method = "HEAD"

        # Parse the Location URI
        uri = urlparse(location)

        if uri.netloc:
            # If there is a netloc, it's an absolute path.
            redirect.host = uri.netloc
            if uri.scheme:
                redirect.protocol = uri.scheme
            if uri.path:
                redirect.path = uri.path

        elif uri.path:
            # If no netloc, but there is a path, resolve from last.
            redirect.host = request.host
            redirect.path = urljoin(request.path, uri.path)

        # Always add the query.
        if uri.query:
            redirect.query += parse_qs(uri.query)

        print("\n[...redirecting...]")
        self.redirect_count += 1
        self._start_request(redirect)
        return

    def _handle_response_view(self, filepath, status_line, body_only):

        if self.response_view.is_loading():
            fn = lambda: self._handle_response_view(filepath, status_line,
                                                    body_only)
            sublime.set_timeout(fn, 100)

        else:
            view = self.response_view
            view.set_name(status_line)

            # Delete the temp file.
            os.remove(filepath)

            # Select the body.
            if body_only:
                selection = sublime.Region(0, view.size())
            else:
                eol = util.get_end_of_line_character(view)
                headers = view.find(eol * 2, 0)
                selection = sublime.Region(headers.b, view.size())

            view.sel().clear()
            view.sel().add(selection)

            # Run response commands and finish.
            self._run_response_commands()
            self._complete("Request complete. " + status_line)

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

    def _run_response_commands(self):
        view = self.response_view
        commands = self.settings.get("response_commands", [])
        for command in commands:
            command = self._normalize_command(command)
            if command:
                view.run_command(command["name"], command["args"])
