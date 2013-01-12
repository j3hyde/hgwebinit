#!/usr/bin/env python
# vim: sw=4 smarttab expandtab :
import BaseHTTPServer
import CGIHTTPServer
import cgitb; cgitb.enable()  ## This line enables CGI error reporting
from CGIHTTPServer import CGIHTTPRequestHandler


def run():
    server = BaseHTTPServer.HTTPServer
    handler = CGIHTTPServer.CGIHTTPRequestHandler
    server_address = ("", 8000)
    handler.cgi_directories = [""]

httpd = server(server_address, handler)
httpd.serve_forever()




if __name__ == '__main__':
    run()
