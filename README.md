# RESTer

HTTP client for Sublime Text

RESTer allows you to build an HTTP request in Sublime Text and view the response in a new tab.

## Using

A request can be as simple as a URI:

```
http://api.my-example-site.com
```

Or, you can send headers and a body:

```
PUT /my-endpoint HTTP/1.1
Host: api.my-example-site.com
Accept: text/plain
Accept-Charset: utf-8
X-custom-header: whatever you want

Here is the payload for the PUT request. Just add an empty line after the headers.
```

Once you have a request ready, use shortcut `Ctrl + Alt + r` or open the Command Palette (`Shift + Command + P`) and enter `RESTer HTTP Request`.

## Installation

### Sublime Package Control

You can install RESTer using the excellent [Package Control][] package manager for Sublime Text:

1. Open "Package Control: Install Package" from the Command Palette (`Shift + Command + P`).
2. Select the "RESTer" option to install RESTer.

[Package Control]: http://wbond.net/sublime_packages/package_control

### Git Installation

To install, clone to your "Packages" directory.

```
git clone git@github.com:pjdietz/rester-sublime-http-client.git
```

## Making Requests

### The Request Line

The first non-empty line of the selection (or document if nothing is selected) is the "request line". RESTer parses this to determine the method, URI, and protocol.

You may include the hostname in the request line, but RESTer does not require it. If omitted, be sure to include a `Host` header indicating the hostname.

Here are some example request lines:

```
GET /my-endpoint HTTP/1.1
Host: api.my-example-site.com
```

```
GET http://api.my-example-site.com/my-endpoint
```

```
http://api.my-example-site.com/my-endpoint
```

```
api.my-example-site.com/my-endpoint
```

Because GET is the default method, each of these will have the same effect.

### Headers

RESTer parses the lines immediately following the first non-empty line up to the first empty line as headers. Use the standard `field-name: field-value` format.

### Query Parameters

For requests with many query parameters, you may want to spread your request across a number of lines. RESTer will parse any lines in the headers section that begin with `?` or `&` as query parameters. You may use `=` or `:` to separate the key from the value.

The following example requests are equivalent:

All in the URI
```
http://api.my-example-site.com/?cat=molly&dog=bear
```

With new lines
```
http://api.my-example-site.com/
?cat=molly
&dog=bear
```

Indented, using colons, and only using ?
```
http://api.my-example-site.com/
    ? cat: molly
    ? dog: bear
```

#### Percent Encoding

One thing to note is that RESTer assumes that anything you place directly in the request line is the way you want it, but query parameters added on individual lines are assumed to be in plain text. So, values of query parameters added on individual lines are percent encoded.

These requests are equivalent:

```
http://api.my-example-site.com/?item=I520like%20spaces
```

```
http://api.my-example-site.com/
    ? item: I like spaces
```


### Body

To supply a message body for POST and PUT requests, add an empty line after the last header. RESTer will treat all content that follows the blank line as the request body.

Here's an example of adding a new cat representation by supplying JSON:

```
POST http://api.my-example-site.com/cats/

{
    "name": "Molly",
    "color": "Calico",
    "nickname": "Mrs. Puff"
}
```

#### Form Encoding

For `application/x-www-form-urlencoded` requests, you can use the `auto_form_encode` command (part of RESTer) to automatically encode a body of key-value pairs. To use this functionality, make sure that `auto_form_encode` is enabled as a [`request_command`](#request-commands) and include a `Content-type: application/x-www-form-urlencoded` header.

The key-value pairs must be on separate lines. You may use `=` or `:` to separate the key from the value. As with query parameters, whitespace around the key and value is ignored.

Example:

```
POST http://api.my-example-site.com/cats/
Content-type: application/x-www-form-urlencoded

name=Molly
color=Calico
nickname=Mrs. Puff
```

Colons and whitespace

```
POST http://api.my-example-site.com/cats/
Content-type: application/x-www-form-urlencoded

      name: Molly
     color: Calico
  nickname: Mrs. Puff
```

### Comments

You may include comments in your request by adding lines in the headers section that begin with `#`. RESTer will ignore these lines.

```
GET /my-endpoint HTTP/1.1
Host: /api.my-example-site.com
# This is a comment.
Cache-control: no-cache
```

## Settings

RESTer has some other features that you can customize through settings. To customize, add the desired key to the user settings file.

You may also provide configuration settings for the current request by adding lines to the headers section that begin with `@`.

The format of the line is `@{name}: {value}` where `{name}` is the key for a setting and `{value}` is the value. The value is parsed as a chunk of JSON.

```
GET /my-endpoint HTTP/1.1
Host: /api.my-example-site.com
@timeout: 2
@default_response_encodings: ["utf-8", "ISO-8859-1", "ascii"]
```

### Displaying the Response and Request

By default, RESTer outputs the request and response to the console and opens a new buffer where it writes the full contents of the response. You can change this behavior by tweaking several settings.

Setting                 | Default | Description
----------------------- | ------- | -----------
output_request          | `true`  | Write the request to the console.
output_response_headers | `true`  | Write the status line and headers to the console.
output_response_body    | `true`  | Write the body of response to the console. **Note**: because [response commands](#response-commands) must by run in a buffer, the body is not processed.
response_buffer         | `true`  | Open a new buffer, write the response, and run any number of [response commands](#response-commands) on the response body.
body_only               | `false` | When writing the response to the buffer, do not include headers.

### Protocol

As of version 1.3.0, RESTer supports making HTTP and HTTPS requests. To use HTTPS, you can include the protocol in the request line. You can also set a default protocol in the settings.

```json
{
    "protocol": "https"
}
```

You may also set the protocol using an override. These requests are equivalent:

```
GET https://api.my-secure-example-site.com/my-endpoint
```

```
GET /my-endpoint
Host: api.my-secure-example-site.com
@protocol:https
```

**Note for Linux Users:** The Python interpreter in Sublime Text on Linux does not have SSL support. To make HTTPS requests, you will need to change the RESTer settings to use [cURL](#curl).

### Port

RESTer will assume ports 80 and 443 for HTTP and HTTPS respectively. If you ofter require a specific custom port, you can set it in the settings.

### Default Headers

To include a set of headers with each request, add them to the `"default_headers"` setting. This is a dictionary with the header names as the keys.

```json
{
    "default_headers": {
        "Accept-Encoding": "gzip, deflate",
        "Cache-control": "no-cache"
    }
}
```

### Default Response Encodings

RESTer can try to discern the encoding for a response. This doesn't always work, so it's a good idea to give it some encodings to try. Do this by supplying a list for the `"default_response_encodings"` setting.

```json
{
    "default_response_encodings": ["utf-8", "ISO-8859-1", "ascii"]
}
```

### Response Commands

After RESTer writes the response into a new tab, it selects the response body. With the body selected, it can perform a series of operations on the text. For example, you could instruct RESTer to pretty-print JSON responses.

To specify commands for RESTer to run on the response, add entries to the `response_commands` member of the settings. The value for `response_commands` must be a list of string names of commands.

```json
{
    "response_commands": ["prettyjson"]
}
```

If you don't have the [PrettyJson](https://github.com/dzhibas/SublimePrettyJson) package installed, nothing bad will happen. You won't get any errors, but you won't get any pretty printed JSON either.

If you're not sure what the command is for a given feature, you may be able to read its name from the command history. Run the command as you normally would, then open  the Python console (`Ctrl` + <code>\`</code>), and enter `view.command_history(0)`. You should see the last command that was run on the current view.

```python
>>> view.command_history(0)
('insert', {'characters': '\n\n'}, 1)
```

### Request Commands

RESTer can perform operations on the text of your request before it parses it. These commands are undone after the request is made, so your file is never modified. As with response commands, you'll specify these by adding a list entry to the settings file. This time, the setting name is `request_commands`.

```json
{
    "request_commands": ["merge_variables"]
}
```

A useful command to use as a request command is `merge_variables` from my [Merge Variables](https://github.com/pjdietz/sublime-merge-variables) package. Using Merge Variables, you can write your requests using placeholder variables that are not expanded until the moment you make the request. Merge Variables allows you to specify multiple configurations as well, so you can build a request once, and have it merge in various configurations. For example, you could start with this request:

```
GET http://{{API}}/my-endpoint
```

For a development configuration, this could expand to:

```
GET http://dev.my-example-site.com/my-endpoint
```

And for a production configuration:

```
GET http://api.my-example-site.com/my-endpoint
```

See [Merge Variables](https://github.com/pjdietz/sublime-merge-variables) for more information.

### Request and Response Commands with Parameters

Most of the time, you'll only need to supply the name for a command. Some commands can take parameters, and you can pass these in by supplying an object instead of a string for your command. To use the object format, be sure to include the name of the command as the `name` member, and any parameters as the `args` member.

```json
{
    "name": "merge_variables",
    "args": {
        "active_sets": ["mysite", "mysite-dev"]
    }
}
```

### Redirects

RESTer will follow redirects automatically. To disable this or limit the response codes which will trigger an automatic redirect, modify these settings (defaults shown):

```json
{
    "follow_redirects": true,
    "follow_redirect_status_codes": [300, 301, 302, 303, 307]
}
```

### cURL

If you have [cURL](http://curl.haxx.se/) installed, you can set RESTer to use cURL instead of the Python `http.client` library. Most users will not need to do this, but this may be helpful for Linux users that are unable to make HTTPS requests because Python was not compiled with SSL support. Or, if you're familiar with using cURL on the command line, you may find it useful to add custom arguments to the cURL command.

There are three settings related to cURL. The first is `http_client` which tells RESTer which client to use (allowed values are `python` for the native Python connector or `curl` for cURL.).

Next is `curl_command` which is the path to the cURL executable. On OSX and Linux, if `curl` is on your path, you will not need to change this. Windows users providing a full path to `curl.exe` will need to use forward slashes in the path (e.g., `C:/curl/curl.exe`).

The last setting is `curl_options`, an optional list of arguments to pass to the `curl` executable. Each option must be a separate string, so to send a custom header, use `["--header", "X-custom-header: header-value"]`, not `"--header X-custom-header: header-value"`. Here's an example showing these three settings:

```json
{
    "http_client": "curl",
    "curl_command": "C:/curl/curl.exe",
    "curl_options": ["--header", "X-custom-header: header-value"]
}
```

For more information on cURL, see the [cURL man page](http://curl.haxx.se/docs/manpage.html)

## Author

**PJ Dietz**

+ [http://pjdietz.com](http://pjdietz.com)
+ [http://github.com/pjdietz](http://github.com/pjdietz)
+ [http://twitter.com/pjdietz](http://twitter.com/pjdietz)

## Copyright and license
Copyright 2013 PJ Dietz

[MIT License](LICENSE)
