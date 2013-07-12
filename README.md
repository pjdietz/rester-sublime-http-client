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

You may include the hostname in the request line, but RESTer does not require it. If omitted, be sure to include a **Host** header indicating the hostname.

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

RESTer parses the lines immediately following the first non-empty line up to the first empty line as headers. Use the standard **field-name: field-value** format.

### Body

To supply a message body for POST and PUT requests, add an empty line after the last header.



