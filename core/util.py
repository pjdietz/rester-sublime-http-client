"""
Utility functions
"""


def get_end_of_line_character(view):
    """Return the EOL character from the view's settings."""
    line_endings = view.settings().get("default_line_ending")
    if line_endings == "windows":
        return "\r\n"
    elif line_endings == "mac":
        return "\r"
    else:
        return "\n"


def get_query_string(query_map):
    """Return the query string given a map of key-value pairs."""
    if query_map:
        query = []
        for (name, values) in query_map.items():
            for value in values:
                query.append(name + "=" + value)
        return "&".join(query)
    return None


def normalize_line_endings(string, eol):
    """Return a string with consistent line endings."""
    string = string.replace("\r\n", "\n").replace("\r", "\n")
    if eol != "\n":
        string = string.replace("\n", eol)
    return string
