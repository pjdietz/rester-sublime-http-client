try:
    # Sublime Text 3
    from RESTer.core import util
except ImportError:
    # Sublime Text 2
    from core import util


class Message:

    def __init__(self):
        self.headers = {}
        self.body = None

    @property
    def header_lines(self):
        lines = []
        for key in self.headers:
            lines.append("%s: %s" % (key, self.headers[key]))
        return lines

    def get_header(self, header):
        header = header.lower()
        for key in self.headers:
            if key.lower() == header:
                return self.headers[key]
        return None

class Request(Message):

    def __init__(self):
        Message.__init__(self)
        self._host = None
        self.protocol = "http"
        self.method = "GET"
        self.path = "/"
        self.port = None
        self.query = {}

    def __str__(self):
        """
        Return a string representation of the request.
        """
        lines = [self.request_line] + self.header_lines
        string = "\n".join(lines)
        if self.body:
            string += "\n\n" + self.body
        return string

    @property
    def host(self):
        return self._host

    @host.setter
    def host(self, host):
        self._host = host
        self.headers["Host"] = host

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


class Response(Message):

    def __init__(self):
        Message.__init__(self)
        self.protocol = "HTTP/1.1"
        self.status = None
        self.reason = None

    def __str__(self):
        """
        Return a string representation of the request.
        """

        lines = [self.status_line] + self.header_lines
        string = "\n".join(lines)
        if self.body:
            string += "\n\n" + self.body
        return string

    @property
    def status_line(self):
        return "%s %d %s" % (self.protocol, self.status, self.reason)
