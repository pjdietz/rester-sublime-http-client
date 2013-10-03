import threading

try:
    # Sublime Text 3
    from http.client import HTTPConnection
    from http.client import HTTPSConnection
except ImportError:
    # Sublime Text 2
    from httplib import HTTPConnection
    from httplib import HTTPSConnection


class HttpRequestThread(threading.Thread):

    def __init__(self, request, settings, encoding="UTF8"):
        threading.Thread.__init__(self)
        self.request = request
        self.encoding = encoding
        self.timeout = settings.get("timeout", None)
        self.output_request = settings.get("output_request", True)
        self.output_response = settings.get("output_response", True)
        self.message = None
        self.success = False

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

        # Output the request to the console.
        if self.output_request:
            print("[Request]")
            print(self.request)

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

        self.success = True
        self.body = resp.read()
        self.response = resp
        conn.close()
