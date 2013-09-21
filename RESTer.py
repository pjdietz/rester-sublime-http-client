import http.client
import gzip
import json
import os
import re
import socket
import tempfile
import threading
import urllib.parse
import zlib

import sublime
import sublime_plugin


RE_METHOD = """(?P<method>[A-Z]+)"""
RE_URI = """(?P<uri>[a-zA-Z0-9\-\/\.\_\:\?\#\[\]\@\!\$\&\=]+)"""
RE_PROTOCOL = """(?P<protocol>.*)"""
RE_ENCODING = """(?:encoding|charset)=['"]*([a-zA-Z0-9\-]+)['"]*"""
RE_OVERRIDE = """^\s*@\s*([^\:]*)\s*:\s*(.*)$"""
SETTINGS_FILE = "RESTer.sublime-settings"


def get_end_of_line_character(view):
    """Return the EOL character from the view's settings."""
    line_endings = view.settings().get("default_line_ending")
    if line_endings == "windows":
        return "\r\n"
    elif line_endings == "mac":
        return "\r"
    else:
        return "\n"


def get_query_string(query_map):
    # Return the query string given a map of key-value pairs.
    if query_map:
        query = []
        for (name, values) in query_map.items():
            for value in values:
                query.append(name + "=" + value)
        return "&".join(query)
    return None


def normalize_line_endings(string, eol):
    """Return a string with consistent line endings."""
    string = string.replace("\r\n", "\n").replace("\r", "\n")
    if eol != "\n":
        string = string.replace("\n", eol)
    return string


def scan_string_for_encoding(string):
    """Read a string and return the encoding identified within."""
    m = re.search(RE_ENCODING, string)
    if m:
        return m.groups()[0]
    return None


def scan_bytes_for_encoding(bytes):
    """Read a byte sequence and return the encoding identified within."""
    m = re.search(RE_ENCODING.encode('ascii'), bytes)
    if m:
        encoding = m.groups()[0]
        return encoding.decode('ascii')
    return None


def decode(bytes, encodings):
    """Return the first successfully decoded string or None"""
    for encoding in encodings:
        try:
            body = bytes.decode(encoding)
            return body
        except UnicodeDecodeError:
            # Try the next in the list.
            pass
    raise DecodeError


class ResterHttpRequestCommand(sublime_plugin.WindowCommand):

    def run(self):

        # Store references.
        self._request_view = self.window.active_view()
        self._eol = get_end_of_line_character(self._request_view)
        self._settings = self._get_settings()

        # Perform commands on the request.
        # Store the number of changes made so we can undo them.
        changes = self._request_view.change_count()
        self._run_request_commands()
        changes = self._request_view.change_count() - changes

        # Read the selected text.
        text = self._get_selection()

        # Undo the request commands to return to the starting state.
        for i in range(changes):
            self._request_view.run_command("undo")

        # Determine the encoding of the editor starting the request.
        # Sublime returns "Undefined" for views that are not yet saved.
        encoding = self._request_view.encoding()
        if not encoding or encoding == "Undefined":
            encoding = "UTF8"

        # Create, start, and handle a thread for the selection.
        thread = HttpRequestThread(text, self._eol, self._settings, encoding)
        thread.start()
        self._handle_thread(thread)

    def _get_selection(self):
        # Return the selected text or the entire buffer.
        view = self._request_view
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
        text = normalize_line_endings(text, self._eol)
        headers = text.split(self._eol * 2, 1)[0]

        # Build a dictionary of the overrides.
        overrides = {}
        for (name, value) in re.findall(RE_OVERRIDE, headers, re.MULTILINE):
            overrides[name] = json.loads(value)

        # Return an OverrideableSettings object.
        return OverrideableSettings(
            settings=sublime.load_settings(SETTINGS_FILE),
            overrides=overrides)

    def _normalize_command(self, command):

        # Return a well formed dictionary for a request or response command
        valid = False
        if isinstance(command, str):
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
        view = self._request_view
        commands = self._settings.get("request_commands", [])
        for command in commands:
            command = self._normalize_command(command)
            if command:
                view.run_command(command["name"], command["args"])

    def _run_response_commands(self, view):
        commands = self._settings.get("response_commands", [])
        for command in commands:
            command = self._normalize_command(command)
            if command:
                view.run_command(command["name"], command["args"])

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
            self._request_view.set_status("rester", message)
            sublime.set_timeout(lambda:
                                self._handle_thread(thread, i, dir), 100)

        elif thread.success:
            # Success.
            self._complete_thread(thread)

        else:
            # Failed.
            self._request_view.erase_status("rester")
            if thread.message:
                sublime.status_message(thread.message)
            else:
                sublime.status_message("Unable to make request.")

    def _complete_thread(self, thread):

        # Read headers and body.
        status_line = self._read_status_line(thread.response)
        header_lines = self._read_header_lines(thread.response)
        headers = self._eol.join([status_line] + header_lines)
        body = self._read_body(thread)

        # Output the response to the console.
        output_headers = self._settings.get("output_response_headers", True)
        output_body = self._settings.get("output_response_body", True)
        if output_headers or output_body:
            print("[Response]")
            if output_headers:
                print(headers)
            if output_headers and output_body:
                print()
            if output_body:
                print(body)

        # Stop now if the user does not want a response buffer.
        if not self._settings.get("response_buffer", True):
            return

        # Open a temporary file to write the response to.
        tmpfile = tempfile.NamedTemporaryFile("w", encoding="UTF8",
                                              delete=False)

        # Body only, but only on success.
        if self._settings.get("body_only", False) and \
                200 <= thread.response.status <= 299:
            tmpfile.write(body)
            body_only = True

        # Status line and headers. Store the file length.
        else:
            tmpfile.write(headers)
            tmpfile.write(self._eol * 2)
            tmpfile.write(body)
            body_only = False

        # Close the file.
        tmpfile.close()

        # Start a new thread to open it asynchronously.
        tmpfile_thread = OpenTempfileThread(self.window, tmpfile.name,
                                            body_only, status_line)
        tmpfile_thread.start()
        self._handle_openfile_thread(tmpfile_thread)

    def _read_status_line(self, response):
        # Build and return the status line (e.g., HTTP/1.1 200 OK)
        protocol = "HTTP"
        if response.version == 11:
            version = "1.1"
        else:
            version = "1.0"
        return "%s/%s %d %s" % (protocol, version, response.status,
                                response.reason)

    def _read_header_lines(self, response):
        # Build and return the header lines
        headers = []
        for (key, value) in response.getheaders():
            headers.append("%s: %s" % (key, value))
        return headers

    def _read_body(self, thread):
        # Decode the body from a list of bytes
        body_bytes = self._unzip_body(thread.body, thread.response)
        body = self._decode_body(body_bytes, thread.response)
        body = normalize_line_endings(body, self._eol)
        return body

    def _unzip_body(self, body_bytes, response):
        content_encoding = response.getheader("content-encoding")
        if content_encoding:
            content_encoding = content_encoding.lower()
            if "gzip" in content_encoding:
                body_bytes = gzip.decompress(body_bytes)
            elif "deflate" in content_encoding:
                # Negatie wbits to supress the standard gzip header.
                body_bytes = zlib.decompress(body_bytes, -15)
        return body_bytes

    def _decode_body(self, body_bytes, response):

        # Decode the body. The hard part here is finding the right encoding.
        # To do this, create a list of possible matches.
        encodings = []

        # Check the content-type header, if present.
        content_type = response.getheader("content-type")
        if content_type:
            encoding = scan_string_for_encoding(content_type)
            if encoding:
                encodings.append(encoding)

        # Scan the body
        encoding = scan_bytes_for_encoding(body_bytes)
        if encoding:
            encodings.append(encoding)

        # Add any default encodings not already discovered.
        default_encodings = self._settings.get(
            "default_response_encodings", [])
        for encoding in default_encodings:
            if encoding not in encodings:
                encodings.append(encoding)

        # Decoding using the encodings discovered.
        try:
            body = decode(body_bytes, encodings)
        except DecodeError:
            body = "{Unable to decode body}"

        return body

    def _handle_openfile_thread(self, thread, i=0, dir=1):

        if thread.is_alive():
            # This animates a little activity indicator in the status area.
            before = i % 8
            after = 7 - before
            if not after:
                dir = -1
            if not before:
                dir = 1
            i += dir
            message = "RESTer loading [%s=%s]" % (" " * before, " " * after)
            self._request_view.set_status("rester", message)
            sublime.set_timeout(lambda:
                                self._handle_openfile_thread(thread, i, dir),
                                100)

        else:
            self._run_response_commands(thread.view)
            self._request_view.erase_status("rester")
            sublime.status_message("RESTer Request Complete")


class HttpRequestThread(threading.Thread):
    """Thread sublcass for making an HTTP request given a string."""

    def __init__(self, string, eol, settings, encoding):
        """Create a new request object

        @param string: The text of the request to perform, including headers,
            settings overrides, etc.
        @type string: str

        @param eol: The line ending character used throughout string
        @type string: str

        @param settings: A Sublime settings instance
        @type settings: sublime.Settings
        """

        threading.Thread.__init__(self)

        # Store members and set defaults.
        self._settings = settings
        self._eol = eol
        self._scheme = "http"
        self._hostname = None
        self._path = None
        self._port = 80
        self._query = {}
        self._method = "GET"
        self._header_lines = []
        self._headers = self._settings.get("default_headers", {})
        if not isinstance(self._headers, dict):
            self._headers = {}
        self._body = None
        self._encoding = encoding
        self.success = False
        self.message = ""

        # Parse the string to fill in the members with actual values.
        self._parse_request(string)

    def run(self):
        """Method to run when the thread is started."""

        # Fail if the hostname is not set.
        if not self._hostname:
            self.result = "Unable to make request. Please provide a hostname."
            return

        # Create the connection.
        timeout = self._settings.get("timeout")
        conn = http.client.HTTPConnection(self._hostname,
                                          port=self._port,
                                          timeout=timeout)
        # Convert the body to bytes
        body_bytes = None
        if self._body:
            body_bytes = self._body.encode(self._encoding)

        try:
            conn.request(self._method,
                         self._get_requet_uri(),
                         headers=self._headers,
                         body=body_bytes)

        except ConnectionRefusedError:
            self.message = "Connection refused."
            self.success = False
            conn.close()
            return

        except socket.gaierror:
            self.message = "Unable to make request. "
            self.message += "Make sure the hostname is valid."
            self.success = False
            conn.close()
            return

        # Output the request to the console.
        if self._settings.get("output_request", True):
            print("[Request]")
            print(self._get_request_as_string())

        # Read the response.
        try:
            resp = conn.getresponse()
        except socket.timeout:
            self.message = "Request timed out."
            self.success = False
            conn.close()
            return

        self.success = True
        self.body = resp.read()
        self.response = resp
        conn.close()

    def _get_requet_uri(self):
        # Return the path + query string for the request.
        uri = self._path
        if self._query:
            uri += "?" + get_query_string(self._query)
        return uri

    def _get_request_as_string(self):

        # Return a string representation of the request.
        lines = []
        lines.append("%s %s HTTP/1.1" % (self._method, self._get_requet_uri()))
        for key in self._headers:
            lines.append("%s: %s" % (key, self._headers[key]))

        string = self._eol.join(lines)

        if self._body:
            string += self._eol + self._body

        return string

    def _parse_request(self, string):

        # Determine instance members from the contents of the string.

        # Pre-parse clean-up.
        string = string.lstrip()
        string = normalize_line_endings(string, self._eol)

        # Split the string into lines.
        lines = string.split(self._eol)

        # Parse the first line as the request line.
        self._parse_request_line(lines[0])

        # All lines following the request line are headers until an empty line.
        # All content after the empty line is the request body.
        has_body = False
        for i in range(1, len(lines)):
            if lines[i] == "":
                has_body = True
                break

        if has_body:
            self._header_lines = lines[1:i]
            self._body = self._eol.join(lines[i+1:])
        else:
            self._header_lines = lines[1:]

        # Make a dictionary of headers.
        self._parse_header_lines()

        # Check if a Host header was supplied.
        has_host_header = False
        for key in self._headers:
            if key.lower() == "host":
                has_host_header = True
                # If self._hostname is not yet set, read it from the header.
                if not self._hostname:
                    self._hostname = self._headers[key]
                break

        # Add a host header, if not explicitly set.
        if not has_host_header and self._hostname:
            self._headers["Host"] = self._hostname

        # If there is still no hostname, but there is a path, try re-parsing
        # the path with // prepended.
        #
        # From the Python documentation:
        # Following the syntax specifications in RFC 1808, urlparse recognizes
        # a netloc only if it is properly introduced by ‘//’. Otherwise the
        # input is presumed to be a relative URL and thus to start with a path
        # component.
        #
        if not self._hostname and self._path:
            uri = urllib.parse.urlparse("//" + self._path)
            self._hostname = uri.hostname
            self._path = uri.path

    def _parse_request_line(self, line):

        # Parse the first line as the request line.
        # Fail, if unable to parse.
        request_line = self._read_request_line_dict(line)
        if not request_line:
            return

        # Parse the URI.
        uri = urllib.parse.urlparse(request_line["uri"])

        # Copy from the parsed URI.
        if uri.scheme:
            self._scheme = uri.scheme
        self._hostname = uri.hostname
        self._path = uri.path
        self._query = urllib.parse.parse_qs(uri.query)
        if uri.port:
            self._port = uri.port

        # Read the method from the request line. Default is GET.
        if "method" in request_line:
            self._method = request_line["method"]

    def _parse_header_lines(self):

        # Parse the lines before the body. Build self._headers dictionary

        headers = {}

        for header in self._header_lines:
            header = header.lstrip()

            # Skip comments and overrides.
            if header[0] in ("#", "@"):
                pass

            # Query parameters begin with ? or &
            elif header[0] in ("?", "&"):

                if "=" in header:
                    (key, value) = header[1:].split("=", 1)
                elif ":" in header:
                    (key, value) = header[1:].split(":", 1)
                else:
                    key, value = None, None

                if key and value:
                    key = key.strip()
                    value = urllib.parse.quote(value.strip())
                    if key in self._query:
                        self._query[key].append(value)
                    else:
                        self._query[key] = [value]

            # All else are headers
            elif ":" in header:
                (key, value) = header.split(":", 1)
                headers[key] = value.strip()

        # Merge headers with default headers provided in settings.
        if headers and self._headers:
            self._headers = dict(list(self._headers.items()) +
                                 list(headers.items()))

    def _read_request_line_dict(self, line):

        # Return a dicionary containing information about the request.

        # method-uri-protocol
        # Ex: GET /path HTTP/1.1
        m = re.search(RE_METHOD + " " + RE_URI + " " + RE_PROTOCOL, line)
        if m:
            return m.groupdict()

        # method-uri
        # Ex: GET /path HTTP/1.1
        m = re.search(RE_METHOD + " " + RE_URI, line)
        if m:
            return m.groupdict()

        # uri
        # Ex: /path or http://hostname/path
        m = re.search(RE_URI, line)
        if m:
            return m.groupdict()

        return None


class OpenTempfileThread(threading.Thread):
    """Thread sublcass for opening a tempfile and selecting the body"""

    def __init__(self, window, filepath, body_only, status_line):
        threading.Thread.__init__(self)
        self.window = window
        self.filepath = filepath
        self.body_only = body_only
        self.status_line = status_line

    def run(self):

        self.view = self.window.open_file(self.filepath, sublime.TRANSIENT)

        # Block while loading.
        while self.view.is_loading():
            pass

        self.view.set_name(self.status_line)

        # Delete the temp file.
        os.remove(self.filepath)

        # Select the body.
        if self.body_only:
            selection = sublime.Region(0, self.view.size())
        else:
            eol = get_end_of_line_character(self.view)
            headers = self.view.find(eol * 2, 0)
            selection = sublime.Region(headers.b, self.view.size())

        self.view.sel().clear()
        self.view.sel().add(selection)


class AutoFormEncodeCommand(sublime_plugin.TextCommand):
    """Encode a request as x-www-form-urlencoded"""

    def run(self, edit):
        self._edit = edit
        # Replace the text in each selection.
        for selection in self._get_selections():
            self._replace_text(selection)

    def _get_selections(self):
        # Return a list or Regions for the selection(s).
        sels = self.view.sel()
        if len(sels) == 1 and sels[0].empty():
            return [sublime.Region(0, self.view.size())]
        else:
            return sels

    def _replace_text(self, selection):
        # Replace the selected text with the new version.

        text = self.view.substr(selection)
        eol = get_end_of_line_character(self.view)

        # Quit if there's not body to encode.
        if (eol * 2) not in text:
            return

        (headers, body) = text.split(eol * 2)
        if self._has_form_encoded_header(headers.split(eol)):
            encoded_body = self._get_encoded_body(body.split(eol))
            request = headers + eol + eol + encoded_body
            self.view.replace(self._edit, selection, request)

    def _has_form_encoded_header(self, header_lines):
        for line in header_lines:
            if ":" in line:
                (header, value) = line.split(":", 1)
                if header.lower() == "content-type" \
                        and "x-www-form-urlencoded" in value:
                    return True
        return False

    def _get_encoded_body(self, body_lines):
        # return the form-urlencoded version of the body.

        form = {}

        for line in body_lines:
            line = line.strip()

            if "=" in line:
                (key, value) = line.split("=", 1)
            elif ":" in line:
                (key, value) = line.split(":", 1)
            else:
                key, value = None, None

            if key and value:
                key = key.strip()
                value = urllib.parse.quote(value.strip())
                if key in form:
                    form[key].append(value)
                else:
                    form[key] = [value]

        return get_query_string(form)


class OverrideableSettings():
    """
    Class for adding a layer of overrides on top of a Settings object

    The class is read-only. If a dictionary-like _overrides member is present,
    the get() method will look there first for a setting before reading from
    the _settings member.
    """

    def __init__(self, settings=None, overrides=None):
        self._settings = settings
        self._overrides = overrides

    def set_settings(self, settings):
        self._settings = settings

    def set_overrides(self, overrides):
        self._overrides = overrides

    def get(self, setting, default=None):
        if self._overrides and setting in self._overrides:
            return self._overrides[setting]
        elif self._settings:
            return self._settings.get(setting, default)
        else:
            return default


class DecodeError(Exception):
    pass
