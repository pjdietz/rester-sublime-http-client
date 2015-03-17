import sublime_plugin

class SetSyntaxCommand(sublime_plugin.TextCommand):
    """Wrapper command for setting the syntax of the current view."""
    def run(self, edit, syntax_file):
        self.view.set_syntax_file(syntax_file)
