from ..util import get_end_of_line_character
from ..util import get_query_string

import sublime
import sublime_plugin

try:
    from urllib.parse import quote
except ImportError:
    # Python 2
    from urllib import quote


def encode_form(body_lines):
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
    return get_query_string(form)


def has_form_encoded_header(header_lines):
    """Return if list includes form encoded header"""
    for line in header_lines:
        if ":" in line:
            (header, value) = line.split(":", 1)
            if header.lower() == "content-type" \
                and "x-www-form-urlencoded" in value:
                return True
    return False


class AutoFormEncodeCommand(sublime_plugin.TextCommand):
    """Encode a request as x-www-form-urlencoded"""

    def __init__(self, *args, **kwargs):
        self._edit = None
        sublime_plugin.TextCommand.__init__(self, *args, **kwargs)

    def run(self, edit):
        self._edit = edit
        # Replace the text in each selection.
        for selection in self._get_selections():
            self._replace_text(selection)

    def _get_selections(self):
        # Return a list of Regions for the selection(s).
        sels = self.view.sel()
        if len(sels) == 1 and sels[0].empty():
            return [sublime.Region(0, self.view.size())]
        else:
            return sels

    def _replace_text(self, selection):
        # Replace the selected text with the new version.

        text = self.view.substr(selection)
        eol = get_end_of_line_character(self.view)

        # Quit if there's no body to encode.
        if (eol * 2) not in text:
            return

        (headers, body) = text.split(eol * 2, 1)
        if has_form_encoded_header(headers.split(eol)):
            encoded_body = encode_form(body.split(eol))
            request = headers + eol + eol + encoded_body
            self.view.replace(self._edit, selection, request)
