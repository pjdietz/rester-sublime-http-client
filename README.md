# RESTer

HTTP client for Sublime Text 3

RESTer allows you to build an HTTP request in Sublime Text 3 and view the response in a new tab.

A request can be as simple as a URI:

```
http://www.mysite.com
```

Or, you can send headers and a body:

```
PUT /my-endpoint HTTP/1.1
Host: api.my-site.com
Accept: text/plain
Accept-Charset: utf-8
X-custom-header: whatever you want

Here is the payload for the PUT request. Just add an empty line after the headers.
```

## Installation

To install, clone to your "Packages" directory.

```
git clone git@github.com:pjdietz/rester-sublime-http-client.git
```

## Making Requests

### The Request Line

The first non-empty line of the selection (or document if nothing is selected) is the "request line". RESTer parses this to determine the method, URI, and protocol.

You may include the hostname in the request line, but RESTer does not require it. If omitted, be sure to include a <code>Host</code> header indicating the hostname.

Here are some example request lines:

```
GET /my-endpoint HTTP/1.1
Host: /api.my-site.com

GET http://api.my-site.com/my-endpoint

http://api.my-site.com/my-endpoint

api.my-site.com/my-endpoint
```

Because GET is the default method and HTTP is the default protocol, each of these will have the same effect.

### Headers

RESTer parses the lines immediately following the first non-empty line up to the first empty line as headers. Use the standard <code>field-name: field-value</code> format.

### Body

To supply a message body for POST and PUT requests, add an empty line after the last header.

### Comments

You may include comments in your request by adding lines in the headers section that begin with <code>#</code>. RESTer will ignore these lines.

```
GET /my-endpoint HTTP/1.1
Host: /api.my-site.com
# This is a comment.
Cache-control: no-cache
```

### Per-request Settings

You may also provide configuration settings for the current request by adding lines to the headers section that begin with <code>@</code>.

The format of the line is <code>@{name}: {value}</code> where <code>{name}</code> is the key for a setting and <code>{value}</code> is the value. The value is parsed as a chunk of JSON.

```
GET /my-endpoint HTTP/1.1
Host: /api.my-site.com
@timeout: 2
@default_response_encodings: ["utf-8", "ISO-8859-1", "ascii"]
```

## Settings

RESTer has some other features that you can customize through settings. To customize, add the desired key to the user settings file or add a per-request setting using an <code>@</code> line as described above.

### Default Headers

To include a set of headers with each request, add them to the <code>"default_headers"</code> setting. This is a dictionary with the header names as the keys.

```
// Default headers to add for each request.
"default_headers": {
    "Accept-Encoding": "gzip, deflate",
    "Cache-control": "no-cache"
}
```

### Default Response Encodings

RESTer can try to discern the encoding for a respones. This doesn't always work, so it's a good idea to give it some encodings to try. Do this by supplying a list for the <code>"default_response_encodings"</code> setting.

```
// List of encodings to try if not discernable from the response.
"default_response_encodings": ["utf-8", "ISO-8859-1", "ascii"],
```

### Resonse Body Commands

After RESTer writes the response to the new tab, it can run a number of Sublime commands on the response body. You can configure these commands to run on only certain responses based on the content-type. For example, if the response's content-type is "application/json" or "text/json", RESTer can run the command "prettyjson" on it. (This works best if you have the [PrettyJson](https://github.com/dzhibas/SublimePrettyJson) package installed, of course!)

The <code>"response_body_commands"</code> settings is an array or objects. Each object must have a <code>"commands"</code> member with a value that is an array of commands. The object may optionally have a <code>"content-type"</code> member that has a value that is an array of content-types, any one of which will allow the command to be used.

```
// Commands to run on the body, based on content-type
"response_body_commands": [
    {
        "content-type": [
            "application/json",
            "text/json"
        ],
        "commands": [
            "prettyjson"
        ]
    }
]
```

If you're not sure what the command is for a given feature, take a peak in the package's <code>Default.sublime-commands</code> file. You can test a command out by making a selection, opening the Python console, and entering <code>view.run_command("{command_name}")</code> where <code>{command}</code> is the string name for the command from the <code>Default.sublime-commands</code> file.

See the default settings for the package to configuration options.
