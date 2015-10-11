import re

from .message import Request
from .util import normalize_line_endings

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


def _read_request_line_dict(line):
    """Return a dict containing the method and uri for a request line"""

    # Split the line into words.
    words = line.split(" ")
    method = "GET"
    # If the line contains only one word, assume the line is the URI.
    if len(words) == 1:
        uri = words[0]
    else:
        method = words[0]
        uri = words[1]

    return {
        "method": method,
        "uri": uri
    }


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
        default_headers = self.settings.get("default_headers", {})
        if isinstance(default_headers, dict):
            for header in default_headers:
                self.request.headers.append((header, default_headers[header]))
        elif default_headers:
            for header in default_headers:
                self.request.headers.append(header)

        self.request.host = self.settings.get("host", None)
        self.request.port = self.settings.get("port", None)
        self.request.protocol = self.settings.get("protocol", None)

        # Pre-parse clean-up.
        text = normalize_line_endings(text, self.eol)

        # Split the string into lines.
        lines = text.split(self.eol)

        # Consume empty and comment lines at the top.
        for i in range(len(lines)):
            line = lines[i].strip()
            if line == "" or line[0] == "#":
                pass
            else:
                lines = lines[i:]
                break

        # Parse the first line as the request line.
        self._parse_request_line(lines[0])

        # All lines following the request line are headers until an empty line.
        # All content after the empty line is the request body.
        has_body = False
        i = 0
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
            self.request.host = uri.netloc
            self.request.path = uri.path

        # Set path to / instead of empty.
        if not self.request.path:
            self.request.path = "/"

        return self.request

    def _parse_header_lines(self, header_lines):

        # Parse the lines before the body.
        # Build request headers list.

        headers = []

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
                headers.append((key, value.strip()))

        # Merge headers with default headers provided in settings.
        self.request.headers.extend(headers)

    def _parse_request_line(self, line):

        # Parse the first line as the request line.
        # Fail, if unable to parse.

        request_line = _read_request_line_dict(line)
        if not request_line:
            return

        # Parse the URI.
        uri = urlparse(request_line["uri"])

        # Copy from the parsed URI.
        if uri.scheme:
            self.request.protocol = uri.scheme
        if uri.netloc:
            # Sometimes urlparse leave the port in the netloc.
            if ":" in uri.netloc:
                (self.request.host, self.request.port) = uri.netloc.split(":")
            else:
                self.request.host = uri.netloc
        if uri.port:
            self.request.port = uri.port
        if uri.path:
            self.request.path = uri.path
        if uri.query:
            query = parse_qs(uri.query)
            for key in query:
                self.request.query[key] = query[key]

        # Read the method from the request line. Default is GET.
        if "method" in request_line:
            self.request.method = request_line["method"]
