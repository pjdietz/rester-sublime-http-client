import sublime
import sublime_plugin
from rester import util

try:
    from RESTer.core import util
    from urllib.parse import quote
except ImportError:
    # Sublime Text 2
    from urllib import quote


class AutoFormEncodeCommand(sublime_plugin.TextCommand):

    """Encode a request as x-www-form-urlencoded"""

    def run(self, edit):
        self._edit = edit
        # Replace the text in each selection.
        for selection in self._get_selections():
            self._replace_text(selection)

    def _get_selections(self):
        # Return a list or Regions for the selection(s).
        sels = self.view.sel()
        if len(sels) == 1 and sels[0].empty():
            return [sublime.Region(0, self.view.size())]
        else:
            return sels

    def _replace_text(self, selection):
        # Replace the selected text with the new version.

        text = self.view.substr(selection)
        eol = util.get_end_of_line_character(self.view)

        # Quit if there's not body to encode.
        if (eol * 2) not in text:
            return

        (headers, body) = text.split(eol * 2, 1)
        if self._has_form_encoded_header(headers.split(eol)):
            encoded_body = self._get_encoded_body(body.split(eol))
            request = headers + eol + eol + encoded_body
            self.view.replace(self._edit, selection, request)

    def _has_form_encoded_header(self, header_lines):
        for line in header_lines:
            if ":" in line:
                (header, value) = line.split(":", 1)
                if header.lower() == "content-type" \
                        and "x-www-form-urlencoded" in value:
                    return True
        return False

    def _get_encoded_body(self, body_lines):
        # return the form-urlencoded version of the body.

        form = {}

        for line in body_lines:
            line = line.strip()

            if "=" in line:
                (key, value) = line.split("=", 1)
            elif ":" in line:
                (key, value) = line.split(":", 1)
            else:
                key, value = None, None

            if key and value:
                key = key.strip()
                value = quote(value.strip())
                if key in form:
                    form[key].append(value)
                else:
                    form[key] = [value]

        return util.get_query_string(form)
