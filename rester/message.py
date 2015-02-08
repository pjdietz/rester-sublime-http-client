from . import util


class Message(object):
    """Base class for HTTP messages"""

    def __init__(self):
        self.headers = []
        self.body = ""

    @property
    def header_lines(self):
        lines = []
        for key, value in self.headers:
            lines.append("%s: %s" % (key, value))
        return lines

    def get_header(self, header):
        header = header.lower()
        for key, value in self.headers:
            if key.lower() == header:
                return value
        return None


class Request(Message):
    """Represents an HTTP request"""

    def __init__(self):
        Message.__init__(self)
        self.host = None
        self.protocol = "http"
        self.method = "GET"
        self.path = "/"
        self.port = None
        self.query = {}

    @property
    def full_path(self):
        """Path + query string for the request."""
        uri = self.path
        if self.query:
            uri += "?" + util.get_query_string(self.query)
        return uri

    @property
    def request_line(self):
        """First line, ex: GET /my-path/ HTTP/1.1"""
        return "%s %s HTTP/1.1" % (self.method, self.full_path)

    @property
    def uri(self):
        """Full URI, including protocol"""
        uri = self.protocol + "://" + self.host
        if self.port:
            uri += ":" + str(self.port)
        uri += self.full_path
        return uri


class Response(Message):
    """Represents an HTTP request"""

    def __init__(self):
        Message.__init__(self)
        self.protocol = "HTTP/1.1"
        self.status = 500
        self.reason = None

    @property
    def status_line(self):
        if self.protocol and self.status and self.reason:
            return "%s %d %s" % (self.protocol, self.status, self.reason)
        return None
