from .message import Request
from .util import normalize_line_endings

import re

try:
    # Python 3
    from urllib.parse import urlparse
    from urllib.parse import parse_qs
    from urllib.parse import quote
except ImportError:
    # Python 2
    from urlparse import urlparse
    from urlparse import parse_qs
    from urllib import quote


RE_METHOD = """(?P<method>[A-Z]+)"""
RE_URI = """(?P<uri>[a-zA-Z0-9\-\/\.\_\:\?\#\[\]\@\!\$\&\=]+)"""
RE_PROTOCOL = """(?P<protocol>.*)"""


def _read_request_line_dict(line):
    # Return a dicionary containing information about the request.
    # Ex: GET /path HTTP/1.1
    m = re.search(RE_METHOD + "\s+" + RE_URI + "\s+" + RE_PROTOCOL, line)
    if m:
        return m.groupdict()
    # Ex: GET /path HTTP/1.1
    m = re.search(RE_METHOD + "\s+" + RE_URI, line)
    if m:
        return m.groupdict()
    # Ex: /path or http://hostname/path
    m = re.search(RE_URI, line)
    if m:
        return m.groupdict()
    return None


class RequestParser:

    def __init__(self, settings, eol):
        self.settings = settings
        self.eol = eol
        self.request = None

    def get_request(self, text):
        """Build and return a new Request"""

        # Build a new Request.
        self.request = Request()

        # Set defaults from settings.
        self.request.headers = self.settings.get("default_headers", {})
        self.request.port = self.settings.get("port", None)
        self.request.protocol = self.settings.get("protocol", None)

        # Pre-parse clean-up.
        text = text.lstrip()
        text = normalize_line_endings(text, self.eol)

        # Split the string into lines.
        lines = text.split(self.eol)

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
            header_lines = lines[1:i]
            self.request.body = self.eol.join(lines[i + 1:])
        else:
            header_lines = lines[1:]

        # Make a dictionary of headers.
        self._parse_header_lines(header_lines)

        # Try to set the hostname from the host header, if not yet set.
        if not self.request.host:
            host = self.request.get_header("host")
            if host:
                self.request.host = host

        # If there is still no hostname, but there is a path, try re-parsing
        # the path with // prepended.
        #
        # From the Python documentation:
        # Following the syntax specifications in RFC 1808, urlparse recognizes
        # a netloc only if it is properly introduced by '//'. Otherwise the
        # input is presumed to be a relative URL and thus to start with a path
        # component.
        #
        if not self.request.host and self.request.path:
            uri = urlparse("//" + self.request.path)
            self.request.host = uri.hostname
            self.request.path = uri.path

        # Set path to / instead of empty.
        if not self.request.path:
            self.request.path = "/"

        return self.request

    def _parse_header_lines(self, header_lines):

        # Parse the lines before the body.
        # Build request's headers dictionary

        headers = {}

        for header in header_lines:
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
                    value = quote(value.strip())
                    if key in self.request.query:
                        self.request.query[key].append(value)
                    else:
                        self.request.query[key] = [value]

            # All else are headers
            elif ":" in header:
                (key, value) = header.split(":", 1)
                headers[key] = value.strip()

        # Merge headers with default headers provided in settings.
        if headers and self.request.headers:
            self.request.headers = dict(list(self.request.headers.items()) +
                                        list(headers.items()))
        elif headers:
            self.request.headers = headers

    def _parse_request_line(self, line):

        # Parse the first line as the request line.
        # Fail, if unable to parse.

        request_line = _read_request_line_dict(line)
        if not request_line:
            return

        # Parse the URI.
        uri = urlparse(request_line["uri"])

        # Copy from the parsed URI.
        self.request.host = uri.hostname
        self.request.path = uri.path
        self.request.query = parse_qs(uri.query)
        if uri.scheme:
            self.request.protocol = uri.scheme
        if uri.port:
            self.request.port = uri.port

        # Read the method from the request line. Default is GET.
        if "method" in request_line:
            self.request.method = request_line["method"]
