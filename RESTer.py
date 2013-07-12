import http.client
import gzip
import re
import socket
import threading
from urllib.parse import urlparse

import sublime
import sublime_plugin


# Read the settings.
settings = sublime.load_settings("RESTer.sublime-settings")


def scan_string_for_encoding(string):
    """Read a string and return the encoding identified within."""
    m = re.search('''(?:encoding|charset)=['"]*([a-zA-Z0-9\-]+)['"]*''', string)
    if m:
        return m.groups()[0]
    return None


def scan_bytes_for_encoding(bytes):
    """Read a byte sequence and return the encoding identified within."""
    m = re.search(b'''(?:encoding|charset)=['"]*([a-zA-Z0-9\-]+)['"]*''', bytes)
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
            pass # Try the next in the list.
    return None


class InsertResponseCommand(sublime_plugin.TextCommand):
    """Output a response to a new file.

    This TextCommand is for internal use and not intended for end users.
    
    """

    def run(self, edit, status_line="", headers="", body="", eol="\n"):

        pos = 0
        start = 0
        end = 0

        if status_line:
            pos += self.view.insert(edit, pos, status_line + eol)
        if headers:
            pos += self.view.insert(edit, pos, headers + eol + eol)
        if body:
            start = pos
            pos += self.view.insert(edit, pos, body)
            end = pos

        # Select the inserted response body.
        if start != 0 and end != 0:
            selection = sublime.Region(start, end)
            self.view.sel().clear()
            self.view.sel().add(selection)


class ResterHttpRequestCommand(sublime_plugin.TextCommand):
    """Make an HTTP request. Display the response in a new file."""

    def run(self, edit):
        text = self._get_selection()
        eol = self._get_end_of_line_character()
        thread = HttpRequestThread(text, eol)
        thread.start()
        self._handle_thread(thread)

    def _handle_thread(self, thread, i=0, dir=1):
        
        if thread.is_alive():
            # This animates a little activity indicator in the status area.
            before = i % 8
            after = (7) - before
            if not after:
                dir = -1
            if not before:
                dir = 1
            i += dir
            message = "RESTer [%s=%s]" %(" " * before, " " * after)
            self.view.set_status("rester", message)
            sublime.set_timeout(
                    lambda: self._handle_thread(thread, i, dir), 100)
        elif isinstance(thread.result, http.client.HTTPResponse):
            # Success.
            self._complete_thread(thread.result)
            self.view.erase_status("rester")
            sublime.status_message("RESTer Request Complete")
        elif isinstance(thread.result, str):
            # Failed.
            self.view.erase_status("rester")
            sublime.status_message(thread.result)
        else:
            # Failed.
            self.view.erase_status("rester")
            sublime.status_message("Unable to make request.")

    def _complete_thread(self, response):
        
        # Create a new file.
        view = self.view.window().new_file() 

        eol = self._get_end_of_line_character()

        # Build the status line (e.g., HTTP/1.1 200 OK)
        protocol = "HTTP"
        if response.version == 11:
            version = "1.1"
        else:
            version = "1.0"
        status_line = "%s/%s %d %s" %(protocol, version, response.status, 
                                     response.reason)

        # Build the headers
        headers = []
        for (key, value) in response.getheaders():
            headers.append("%s: %s" %(key, value))
        headers = eol.join(headers)

        # Decode the body from a list of bytes
        body_bytes = response.read()

        # Unzip if needed.
        content_encoding = response.getheader("content-encoding")
        if content_encoding:
            content_encoding = content_encoding.lower()
            if "gzip" in content_encoding:
                body_bytes = gzip.decompress(body_bytes)

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
        default_encodings = settings.get("default_response_encodings")
        for encoding in default_encodings:
            if encoding not in encodings:
                encodings.append(encoding)

        # Decoding using the encodings discovered.        
        body = decode(body_bytes, encodings)
        if body is None:
            print("ERROR!")
            return
            # TODO: Show error message.

        # Normalize the line endings
        body = body.replace("\r\n", "\n").replace("\r", "\n")  
        eol = self._get_end_of_line_character()
        if eol != "\n":
            body = body.replace("\n", eol)

        # Insert the response and select the body.
        if settings.get("body_only") and 200 <= response.status <= 299: 
            # Output the body only, but only on success.
            view.run_command("insert_response", {
                "body": body,
                "eol": eol
            })
        else:
            # Output status, headers, and body.
            view.run_command("insert_response", {
                "status_line": status_line,
                "headers": headers,
                "body": body,
                "eol": eol
            })

        # Read the content-type header, if present.
        actual_content_type = response.getheader("content-type")
        if actual_content_type:
            actual_content_type = actual_content_type.lower()

        # Run commands on the inserted body
        command_list = settings.get("response_body_commands", [])
        for command in command_list:

            run = True

            # If this command has a content-type list, only run if the
            # actual content type matches an item in the list.
            if "content-type" in command:
                run = False
                if actual_content_type:
                    test_content_type = command["content-type"]
                    if isinstance(test_content_type, str):
                        run = actual_content_type == test_content_type.lower()
                    # Check iterable for stringness of all items. 
                    # Will raise TypeError if some_object is not iterable
                    elif all(isinstance(item, str) for item \
                                                    in test_content_type): 
                        run = actual_content_type in [content_type.lower() \
                                for content_type in test_content_type]
                    else:
                        raise TypeError

        if run:
            for commandName in command["commands"]:
                view.run_command(commandName)

    def _get_selection(self):
        """Return the selected text or the entire buffer."""
        sels = self.view.sel()
        if len(sels) == 1 and sels[0].empty():
            # No selection. Use the entire buffer.
            selection = self.view.substr(sublime.Region(0, self.view.size()))
        else:
            # Concatenate the selections into one large string.
            selection = ""
            for sel in sels:
                selection += self.view.substr(sel)
        return selection

    def _get_end_of_line_character(self):
        """Return the EOL character from the view's settings."""
        line_endings = self.view.settings().get("default_line_ending")  
        if line_endings == "windows":
            return "\r\n" 
        elif line_endings == "mac":  
            return "\r"
        else:
            return "\n"


class HttpRequestThread(threading.Thread):
    """Thread sublcass for making an HTTP request given a string."""

    def __init__(self, string, eol="\n"):
        """Create a new request object"""

        threading.Thread.__init__(self)  

        # Store members and set defaults.
        self._eol = eol
        self._scheme = "http"
        self._hostname = None
        self._path = None
        self._query = None
        self._method = "GET"
        self._header_lines = []
        self._headers = settings.get("default_headers", {})
        self._body = None

        # Parse the string to fill in the members with actual values.
        self._parse_string(string)
    
    def run(self):
        """Method to run when the thread is started."""

        # Fail if the hostname is not set.
        if not self._hostname:
            self.result = "Unable to make request: Please provide a hostname."
            return

        # Create the connection.
        conn = http.client.HTTPConnection(self._hostname)

        uri = self._path
        if self._query:
            uri += "?" + self._query
        try:
            conn.request(self._method, uri, headers=self._headers, body=self._body)
        except socket.gaierror:
            self.result = "Unable to make request. Make sure the hostname is valid."
            conn.close()
            return

        # Read the response.
        resp = conn.getresponse()
        conn.close()
        self.result = resp

    def _normalize_line_endings(self, string):  
        """Return a string with consistent line endings."""
        string = string.replace("\r\n", "\n").replace("\r", "\n")  
        if self._eol != "\n":
            string = string.replace("\n", self._eol)
        return string

    def _parse_string(self, string):
        """Determine instance members from the contents of the string."""

        # Pre-parse clean-up.
        string = string.lstrip()
        string = self._normalize_line_endings(string)

        # Split the string into lines.
        lines = string.split(self._eol)

        # The first line is the request line.
        request_line = lines[0]

        # Parse the first line as the request line.
        self._parse_request_line(request_line)

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

        # Check if the Host was supplied in a header.
        if not self._hostname:
            for key in self._headers:
                if key.lower() == "host":
                    self._hostname = self._headers[key]

    def _parse_request_line(self, line):
        """Parse the first line of the request"""

        # Parse the first line as the request line.
        # Fail, if unable to parse.
        request_line = self._read_request_line_dict(line)
        if not request_line:
            return

        # Parse the URI.
        uri = urlparse(request_line["uri"])

        # Copy from the parsed URI.
        self._scheme = uri.scheme
        self._hostname = uri.hostname
        self._path = uri.path
        self._query = uri.query

        # Read the method from the request line. Default is GET.
        if "method" in request_line:
            self._method = request_line["method"]

        # Read the scheme from the URI or request line. Default is http.
        if not self._scheme:
            if "protocol" in request_line:
                protocol = request_line["protocol"].upper()
                if "HTTPS" in protocol:
                    self._scheme = "https"

    def _parse_header_lines(self):
        """Build self._headers dictionary"""
        headers = {}
        for header in self._header_lines:
            if ":" in header:
                (key, value) = header.split(":", 1)
                headers[key] = value.strip()
        self._headers = dict(list(self._headers.items()) + 
                            list(headers.items()))

    def _read_request_line_dict(self, line):
        """Return a dicionary containing information about the request."""

        # TODO Optimize regex

        # method-uri-protocol
        # Ex: GET /path HTTP/1.1
        m = re.search('(?P<method>[A-Z]+) (?P<uri>[a-zA-Z0-9\-\/\.\_\:\?\#\[\]\@\!\$\&\=]+) (?P<protocol>.*)', line)
        if m:
            return m.groupdict()

        # method-uri
        # Ex: GET /path HTTP/1.1
        m = re.search('(?P<method>[A-Z]+) (?P<uri>[a-zA-Z0-9\-\/\.\_\:\?\#\[\]\@\!\$\&\=]+)', line)
        if m:
            return m.groupdict()

        # uri
        # Ex: /path or http://hostname/path
        m = re.search('(?P<uri>[a-zA-Z0-9\-\/\.\_\:\?\#\[\]\@\!\$\&\=]+)', line)
        if m:
            return m.groupdict()

        return None
