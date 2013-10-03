try:
    # Sublime Text 3
    from RESTer.core import util
except ImportError:
    # Sublime Text 2
    from core import util

class Request:

    def __init__(self):
        self.body = None
        self.headers = {}
        self.host = None
        self.method = "GET"
        self.path = "/"
        self.port = None
        self.query = {}

    def __str__(self):

        """
        Return a string representation of the request.
        """

        lines = []
        lines.append("%s %s HTTP/1.1" % (self.method, self.get_full_path()))
        for key in self.headers:
            lines.append("%s: %s" % (key, self.headers[key]))

        string = "\n".join(lines)

        if self.body:
            string += "\n\n" + self.body

        return string

    def get_full_path(self):
        # Return the path + query string for the request.
        uri = self.path
        if self.query:
            uri += "?" + util.get_query_string(self.query)
        return uri


class Response():

    def __init__(self):
        self.protocol = "HTTP/1.1"
        self.status = None
        self.reason = None
        self.body = None
        self.headers = []

    def __str__(self):

        """
        Return a string representation of the request.
        """

        lines = [self.get_status_line()]
        lines += self.headers
        string = "\n".join(lines)
        if self.body:
            string += "\n\n" + self.body
        return string

    def get_status_line(self):
        return "%s %d %s" % (self.protocol, self.status, self.reason)
