import hashlib
import json
import os
import re
import tempfile
import time

from ..overrideable import OverrideableSettings
from ..http import HttpRequestThread
from ..parse import RequestParser
from ..message import Request
from ..util import get_end_of_line_character
from ..util import normalize_line_endings
import sublime
import sublime_plugin

try:
    from urllib.parse import parse_qs
    from urllib.parse import urljoin
    from urllib.parse import urlparse
except ImportError:
    # Python 2
    from urlparse import parse_qs
    from urlparse import urlparse
    from urlparse import urljoin

MAX_REDIRECTS = 10
RE_OVERRIDE = """^\s*@\s*([^\:]*)\s*:\s*(.*)$"""
SETTINGS_FILE = "RESTer.sublime-settings"


def _normalize_command(command):
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


class ResterHttpRequestCommand(sublime_plugin.WindowCommand):
    def __init__(self, *args, **kwargs):
        sublime_plugin.WindowCommand.__init__(self, *args, **kwargs)
        self.encoding = "UTF-8"
        self.eol = "\n"
        self.request_view = None
        self.response_view = None
        self.settings = None
        self._command_hash = None
        self._completed_message = "Done."
        self._redirect_count = 0
        self._requesting = False

    def run(self):

        # Store references.
        self.request_view = self.window.active_view()
        self.response_view = None
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

        # Set the state to requesting.
        self._requesting = True

        # Create a new hash for this specific run of the command.
        command_hash = hashlib.sha1()
        command_hash.update(str(time.time()).encode("ascii"))
        command_hash = command_hash.hexdigest()
        self._command_hash = command_hash
        self.check_if_requesting(command_hash)

        # Make the request.
        self._start_request(request)

    def check_if_requesting(self, command_hash, i=0, direction=1):

        # Ignore if the command hash does not match.
        # That indicates the callback is stale.
        if self._command_hash != command_hash:
            return

        # Show an animation until the command is complete.
        if self._requesting:
            # This animates a little activity indicator in the status area.
            before = i % 8
            after = 7 - before
            if not after:
                direction = -1
            if not before:
                direction = 1
            i += direction
            message = "RESTer [%s=%s]" % (" " * before, " " * after)
            self.request_view.set_status("rester", message)
            fn = lambda: self.check_if_requesting(command_hash, i, direction)
            sublime.set_timeout(fn, 100)
        else:
            if not self._completed_message:
                self._completed_message = "Done."
            self.request_view.set_status("rester", self._completed_message)

    def handle_response_view(self, filepath, status_line, body_only):
        if self.response_view.is_loading():
            fn = lambda: self.handle_response_view(filepath, status_line,
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
                eol = get_end_of_line_character(view)
                headers = view.find(eol * 2, 0)
                selection = sublime.Region(headers.b, view.size())

            view.sel().clear()
            view.sel().add(selection)

            # Run response commands and finish.
            self._run_response_commands()
            self._complete("Request complete. " + status_line)

    def handle_thread(self, thread):
        if thread.is_alive():
            # Working...
            sublime.set_timeout(lambda: self.handle_thread(thread), 100)
        elif thread.success:
            # Success.
            self._complete_thread(thread)
        else:
            # Failed.
            if thread.message:
                self._complete(thread.message)
            else:
                self._complete("Unable to make request.")

    def _complete(self, message):
        # End the command and display a message.
        self._requesting = False
        self._completed_message = message

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
                print(response.body)

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
                tmpfile.write(response.body)
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
        self.handle_response_view(tmpfile.name, status_line, body_only)

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

    def _follow_redirect(self, response, request):
        # Stop now in the event of an infinite loop.
        if self._redirect_count > MAX_REDIRECTS:
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
        self._redirect_count += 1
        self._start_request(redirect)
        return

    def _run_request_commands(self):
        # Process the request buffer to prepare the contents for the request.
        view = self.request_view
        commands = self.settings.get("request_commands", [])
        for command in commands:
            command = _normalize_command(command)
            if command:
                view.run_command(command["name"], command["args"])

    def _run_response_commands(self):
        view = self.response_view
        commands = self.settings.get("response_commands", [])
        for command in commands:
            command = _normalize_command(command)
            if command:
                view.run_command(command["name"], command["args"])

    def _start_request(self, request):
        # Create, start, and handle a thread for the selection.
        if self.settings.get("output_request", True):
            print("\n[Request]")
            print(request)
        thread = HttpRequestThread(request, self.settings, self.encoding)
        thread.start()
        self.handle_thread(thread)
