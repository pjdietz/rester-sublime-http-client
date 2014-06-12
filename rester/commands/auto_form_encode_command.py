from ..constants import SETTINGS_FILE
from ..util import get_end_of_line_character
from ..util import get_query_string

import sublime
import sublime_plugin

try:
    from urllib.parse import quote
except ImportError:
    # Python 2
    from urllib import quote


def encode_form(body_lines, eol):
    """Return the form-urlencoded version of the body."""

    # Field names as keys, and lists of field values as values.
    form = {}

    # Key and value for multiple field. These are set only while in the
    # process of consuming lines.
    delimited_key = None
    delimited_value = None

    # Read delimiters from settings.
    settings = sublime.load_settings(SETTINGS_FILE)
    form_field_start = settings.get("form_field_start", None)
    form_field_end = settings.get("form_field_end", None)
    delimited = form_field_start and form_field_end

    for line in body_lines:

        key = None
        value = None

        # Currently building delimited field.
        if delimited and delimited_key:

            # Check if this line ends with the closing delimiter.
            if line.rstrip().endswith(form_field_end):

                # Read the line up to the delimiter.
                value = line.rstrip()[:-len(form_field_end)]

                # The field is complete. Prepare to copy this to the form.
                key = delimited_key
                value = delimited_value + eol + value
                delimited_key = None
                delimited_value = None

            # The field is still being built. Append the current line.
            else:
                delimited_value += eol + line

        # No delimited field in progress.
        else:

            # Attempt to parse this line into a key-value pair.
            if "=" in line:
                (key, value) = line.split("=", 1)
            elif ":" in line:
                (key, value) = line.split(":", 1)

            if key and value:

                key = key.strip()

                # Test if this value begins a delimited value.

                # If the field begins with the starting delimiter, copy the
                # contents after that delimiter to a variable.
                if delimited and value.lstrip().startswith(form_field_start):
                    value = value.lstrip()[len(form_field_start):]

                    # If the field ends with the ending delimiter, trim the
                    # delimiter from the end and close field.
                    if value.rstrip().endswith(form_field_end):
                        value = value.rstrip()[:-len(form_field_end)]
                        delimited_key = None
                        delimited_value = None

                    # If the field does NOT end with the delimiter, keep
                    # building the field with subsequent lines.
                    else:
                        delimited_key = key
                        delimited_value = value
                        key = None
                        value = None

                # Normal field.
                else:
                    value = value.strip()

        # As long as key and value are set, add the item to the form
        if key and value:
            value = quote(value)
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
            encoded_body = encode_form(body.split(eol), eol)
            request = headers + eol + eol + encoded_body
            self.view.replace(self._edit, selection, request)
