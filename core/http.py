import re
import socket
import threading
import zlib

try:
    # Sublime Text 3
    from http.client import HTTPConnection
    from http.client import HTTPSConnection
    from RESTer.core import message
    from RESTer.core import util
except ImportError:
    # Sublime Text 2
    from httplib import HTTPConnection
    from httplib import HTTPSConnection
    from core import message
    from core import util


def decode(bytes, encodings):
    """Return the first successfully decoded string or None"""
    for encoding in encodings:
        try:
            decoded = bytes.decode(encoding)
            return decoded
        except UnicodeDecodeError:
            # Try the next in the list.
            pass
    raise DecodeError


class DecodeError(Exception):
    pass


class HttpRequestThread(threading.Thread):

    def __init__(self, request, settings, encoding="UTF8", eol="\n"):
        threading.Thread.__init__(self)
        self.request = request
        self.response = None
        self.message = None
        self.success = False
        self.encoding = encoding
        self.eol = eol
        self.timeout = settings.get("timeout", None)
        self.output_request = settings.get("output_request", True)
        self.output_response = settings.get("output_response", True)
        self._encodings = settings.get("default_response_encodings", [])

    def run(self):
        """Method to run when the thread is started."""

        # Fail if the hostname is not set.
        if not self.request.host:
            self.message = "Unable to make request. Please provide a hostname."
            self.success = False
            return

        # Determine the class to use for the connection.
        if self.request.protocol == "https":
            connection_class = HTTPSConnection
        else:
            connection_class = HTTPConnection

        # Create the connection.
        conn = connection_class(self.request.host,
                                port=self.request.port,
                                timeout=self.timeout)

        # Convert the body to bytes
        body_bytes = None
        if self.request.body:
            body_bytes = self.request.body.encode(self.encoding)

        try:
            conn.request(self.request.method,
                         self.request.get_full_path(),
                         headers=self.request.headers,
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

        # Read the response.
        try:
            resp = conn.getresponse()
        except socket.timeout:
            self.message = "Request timed out."
            self.success = False
            conn.close()
            return
        except:
            self.message = "Unexpected error making request."
            self.success = False
            conn.close()
            return

        # Read the response
        self._read_response(resp)
        conn.close()
        self.success = True

    def _read_response(self, resp):

        # Read the HTTPResponse and populate the response member.
        self.response = message.Response()

        # HTTP/1.1 is the default
        if resp.version == 10:
            self.response.protocol = "HTTP/1.0"

        # Status
        self.response.status = resp.status
        self.response.reason = resp.reason

        # Headers
        self.response.headers = []
        for (key, value) in resp.getheaders():
            self.response.headers.append("%s: %s" % (key, value))

        # Body
        self.response.body = self._read_body(resp.read(), resp)

    def _read_body(self, body_bytes, resp):
        # Decode the body from a list of bytes
        if not body_bytes:
            return None
        body_bytes = self._unzip_body(body_bytes, resp)
        body = self._decode_body(body_bytes, resp)
        body = util.normalize_line_endings(body, self.eol)
        return body

    def _unzip_body(self, body_bytes, resp):
        content_encoding = resp.getheader("content-encoding")
        if content_encoding:
            content_encoding = content_encoding.lower()
            if "gzip" in content_encoding or "defalte" in content_encoding:
                body_bytes = zlib.decompress(body_bytes, 15 + 32)
        return body_bytes

    def _decode_body(self, body_bytes, resp):

        # Decode the body. The hard part here is finding the right encoding.
        # To do this, create a list of possible matches.
        encodings = []

        # Check the content-type header, if present.
        content_type = resp.getheader("content-type")
        if content_type:
            encoding = util.scan_string_for_encoding(content_type)
            if encoding:
                encodings.append(encoding)

        # Scan the body
        encoding = util.scan_bytes_for_encoding(body_bytes)
        if encoding:
            encodings.append(encoding)

        # Add any default encodings not already discovered.
        for encoding in self._encodings:
            if encoding not in encodings:
                encodings.append(encoding)

        # Decoding using the encodings discovered.
        try:
            body = decode(body_bytes, encodings)
        except DecodeError:
            body = "{Unable to decode body}"

        return body
