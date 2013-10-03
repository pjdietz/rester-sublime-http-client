class Message:

    def __init__(self):
        self.body = None
        self.headers = {}

    def __str__(self):
        return self.headers + "\n" + self.body


class Request(Message):

    def __init__(self):
        Message.__init__(self)
        self.host = None
        self.method = "GET"
        self.path = "/"
        self.port = None
        self.query = {}


class Response(Message):

    def __init__(self):
        Message.__init__(self)
        self.statusCode = None
        self.reasonPhrase = None
