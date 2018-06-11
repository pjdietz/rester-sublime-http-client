import codecs
import hashlib
import json
import os
import re
import tempfile
import time

from ..constants import SETTINGS_FILE, SYNTAX_FILE
from ..http import CurlRequestThread
from ..http import HttpClientRequestThread
from ..message import Request
from ..overrideable import OverrideableSettings
from ..parse import RequestParser
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
MAX_GROUPS = 10
RE_OVERRIDE = """^\s*@\s*([^\:]*)\s*:\s*(.*)$"""


def _normalize_command(command):
    # Return a well formed dictionary for a request or response command

    valid = False

    # Find the string class. (str for py3, basestring for py2)
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
        self._request_view_group = None
        self._request_view_index = None

    def run(self, pos=None):
        # Store references.
        self.request_view = self.window.active_view()
        self._request_view_group, self._request_view_index = \
            self.window.get_view_index(self.request_view)
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

        # Store the text before any request commands are applied.
        originalText = self._get_selection(pos)

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
        text = self._get_selection(pos)

        # Undo the request commands to return to the starting state.
        if text != originalText:
            for i in range(changes):
                self.request_view.run_command("undo")

        def replace(m):
            return variables.get(m.group(1), '')
        view = self.request_view
        extractions = []
        view.find_all(r'(?:(#)\s*)?@([_a-zA-Z][_a-zA-Z0-9]*)\s*=\s*(.*)', 0, r'\1\2=\3', extractions)
        variables = {}
        for var in extractions:
            var, _, val = var.partition('=')
            if var[0] != '#':
                variables[var] = val.strip()
        for var in re.findall(r'(?:(#)\s*)?@([_a-zA-Z][_a-zA-Z0-9]*)\s*=\s*(.*)', originalText):
            if var[0] != '#':
                var, val = var[1], var[2]
                variables[var] = val.strip()
        text = re.sub(r'\{\{\s*([_a-zA-Z][_a-zA-Z0-9]*)\s*\}\}', replace, text)

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

    def handle_response_view(self, filepath, title, body_only):
        if self.response_view.is_loading():
            fn = lambda: self.handle_response_view(filepath, title,
                                                   body_only)
            sublime.set_timeout(fn, 100)

        else:
            view = self.response_view
            view.set_scratch(self.settings.get("response_scratch", True))
            view.set_name(title)

            # Delete the temp file.
            os.remove(filepath)

            # Select the body.
            selection = None
            if body_only:
                selection = sublime.Region(0, view.size())
            else:
                eol = get_end_of_line_character(view)
                headers = view.find(eol * 2, 0)
                if headers:
                    selection = sublime.Region(headers.b, view.size())

            if selection:
                view.sel().clear()
                view.sel().add(selection)

            # Run response commands and finish.
            self._run_response_commands()
            self._complete("Request complete. " + title)

            # Close all views in the response group other than the current
            # response view.
            if (not self.settings.get("response_group", None) is None) \
                    and self.settings.get("response_group_clean", False):

                views = self.window.views_in_group(self.window.active_group())
                for other_view in views:
                    if other_view.id() != view.id():
                        self.window.focus_view(other_view)
                        self.window.run_command("close_file")

            # Set the focus back to the request group and view.
            if self.settings.get("request_focus", False):
                self.window.focus_group(self._request_view_group)
                self.window.focus_view(self.request_view)

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
        output_body = self.settings.get("output_response_body", True) and \
            response.body

        if output_headers or output_body:

            if thread.elapsed:
                print("\nResponse time:", thread.elapsed)

            print("\n[Response]")

            if output_headers:
                print(status_line)
                print("\n".join(response.header_lines))

            if output_headers and output_body:
                print("")

            if output_body:
                try:
                    print(response.body)
                except UnicodeEncodeError:
                    # Python 2
                    print(response.body.encode("UTF8"))

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
        # (Note: Using codecs to support Python 2.6)
        tmpfile = tempfile.NamedTemporaryFile("w", delete=False)
        filename = tmpfile.name
        tmpfile.close()
        tmpfile = codecs.open(filename, "w", encoding="UTF8")

        # Body only, but only on success.
        success = 200 <= thread.response.status <= 299
        if success and self.settings.get("body_only", False):
            if response.body:
                tmpfile.write(response.body)
            body_only = True

        # Status line and headers.
        else:

            tmpfile.write(response.status_line)
            tmpfile.write("\n")

            for header in response.header_lines:
                tmpfile.write(header)
                tmpfile.write("\n")

            if response.body:
                tmpfile.write("\n")
                tmpfile.write(response.body)

            body_only = False

        if not response.body:
            body_only = False

        # Close the file.
        tmpfile.close()
        filepath = tmpfile.name

        # Open the file in a new view.
        title = status_line
        if thread.elapsed:
            title += " (%.4f sec.)" % thread.elapsed
        self.response_view = self.window.open_file(filepath)
        self.response_view.set_syntax_file(SYNTAX_FILE)

        # Create, if needed, a group specific for responses and move the
        # response view to that group.
        response_group = self.settings.get("response_group", None)
        if response_group is not None:
            response_group = min(response_group, MAX_GROUPS)
            while self.window.num_groups() < response_group + 1:
                self.window.run_command("new_pane")
            self.window.set_view_index(self.response_view, response_group, 0)
            if not self.settings.get("request_focus", False):
                # Set the focus to the response group.
                self.window.focus_group(response_group)
        self.handle_response_view(tmpfile.name, title, body_only)

    def _get_selection(self, pos=None):
        # Return a string of the selected text or the entire buffer.
        # if there are multiple selections, concatenate them.
        view = self.request_view
        if pos is None:
            sels = view.sel()
            if len(sels) == 1 and sels[0].empty():
                pos = sels[0].a
        if pos is not None:
            selection = view.substr(sublime.Region(0, view.size()))
            begin = selection.rfind('\n###', 0, pos)
            end = selection.find('\n###', pos)
            if begin and end:
                selection = selection[begin:end]
            elif begin:
                selection = selection[begin:]
            elif end:
                selection = selection[:end]
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
            print(request.request_line)
            print("Host: %s" % request.host)
            for header in request.header_lines:
                print(header)
            if request.body:
                print("")
                try:
                    print(request.body)
                except UnicodeEncodeError:
                    # Python 2
                    print(request.body.encode("UTF8"))

        client = self.settings.get("http_client", "python")
        if client == "python":
            thread_class = HttpClientRequestThread
        elif client == "curl":
            thread_class = CurlRequestThread
        else:
            message = "Invalid request_client. "
            message += "Must be 'python' or 'curl'. Found " + client
            self._complete(message)
            return

        thread = thread_class(request, self.settings, encoding=self.encoding)
        thread.start()
        self.handle_thread(thread)


class ResterHttpResponseCloseEvent(sublime_plugin.ViewEventListener):
    @classmethod
    def is_applicable(cls, settings):
        syntax = settings.get('syntax')
        return syntax == SYNTAX_FILE

    @classmethod
    def applies_to_primary_view_only(cls):
        return True

    def on_pre_close(self):
        settings = sublime.load_settings(SETTINGS_FILE)
        response_group = settings.get("response_group", None)
        if response_group is not None:
            response_group = min(response_group, MAX_GROUPS)
            window = self.view.window()
            views = window.views_in_group(response_group)
            if len(views) == 1 and self.view == views[0]:
                window.focus_group(0)
                fn = lambda: window.run_command("close_pane")
                sublime.set_timeout(fn, 0)
