import sublime
import sublime_plugin

class HttpRequestCommand(sublime_plugin.WindowCommand):

    def __init__(self, *args, **kwargs):
        self._member = "Oscar"
        sublime_plugin.WindowCommand.__init__(self,  *args, **kwargs)

    def run(self):
        print("HttpRequestCommand")
        print(self._member)
