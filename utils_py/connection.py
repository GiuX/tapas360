#!/usr/bin/env python
# -*- encoding: utf-8 -*-
import os, sys
if __name__ == '__main__':
    from twisted.internet import glib2reactor as reactor
    reactor.install()
from twisted.internet import defer, reactor
from twisted.internet.protocol import Protocol, ClientFactory
import time, datetime
from gzip import GzipFile
from io import StringIO

import gi
gi.require_version('Gst', '1.0')
from gi.repository import GObject as gobject
import gc
#
from .util import debug

DEBUG = 2

class ClientProtocol(Protocol):
    def __init__(self):
        self._recv_data = ''.encode('utf-8')
        self._header = ''.encode('utf-8')
        self.content_encoding = ''.encode('utf-8')
        self.content_size = 0

    def connectionMade(self):
        debug(DEBUG+1, '%s connectionMade with: %s', self, self.transport.getPeer())
        #self.transport.setTcpKeepAlive(1)
        self.factory.connectionMade(self.transport.getPeer().host)
        
    def makeRequest(self, path, byterange=''):
        debug(DEBUG+1, 'makeRequest: %s %s:%d', path, self.factory.host, 
            self.factory.port)
        if self.factory.port == 80:
            host = self.factory.host
        else:
            host = '%s:%d' %(self.factory.host, self.factory.port)
        s = 'GET %s HTTP/1.1\r\n' %(path) +\
            'Host: %s\r\n' %(host) +\
            'Connection: keep-alive\r\n' +\
            'Cache-Control: no-cache\r\n' +\
            'Pragma: no-cache\r\n'
        if not byterange == '':
            s = s+'Range: bytes='+byterange+'\r\n'
        s = s+'User-Agent:Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/28.0.1500.71 Safari/537.36\r\n' +\
            '\r\n'
        #debug(0, 'makeRequest: %s ', s)
        self.transport.write(s.encode('utf-8'))

    def dataReceived(self, data):
        debug(DEBUG+1, 'dataReceived: %s', len(data))
        
        if data.startswith('HTTP/1.1 404'.encode('utf-8')):
            debug(DEBUG, '%s error 404', self)
            self.factory.emit('error', 'HTTP/1.1 404 response')
            self.transport.loseConnection()
            return
        elif data.startswith('HTTP/1.1 200 OK'.encode('utf-8')) or data.startswith('HTTP/1.1 302 Found'.encode('utf-8')):
            self._recv_data = data
            
        else:
            self._recv_data += data
        # handle response
        if not self._recv_data:
            return
        added_size = len(data)
        if not self._header:
            try:
                self._header, self._recv_data = self._recv_data.split('\r\n\r\n'.encode('utf-8'), 1)
                added_size = len(self._recv_data)
                # print '---------- Header: ' + str(self._header)
                for h in self._header.split('\r\n'.encode('utf-8')):
                    if h.startswith('Content-Length: '.encode('utf-8')):
                        self.content_size = int(h.replace('Content-Length: '.encode('utf-8'), ''.encode('utf-8')).strip())
                    elif h.startswith('Content-Size: '.encode('utf-8')):
                        self.content_size = int(h.replace('Content-Size: '.encode('utf-8'), ''.encode('utf-8')).strip())
                    elif h.startswith('Content-Encoding: '.encode('utf-8')):
                        self.content_encoding = h.replace('Content-Encoding: '.encode('utf-8'), ''.encode('utf-8')).strip()
                    elif h.startswith('Location: '.encode('utf-8')): # Redirect!
                        url = h.replace('Location: '.encode('utf-8'), ''.encode('utf-8')).strip()
                        self.transport.loseConnection()
                        self.factory.emit('url-redirect', url)

                    #elif h.startswith('X-Cache:'):
                    #    print h.replace('X-Cache: ', '')
            except ValueError:
                return
        #
        if self.content_size == len(self._recv_data) and self.content_size > 0:
            if self.content_encoding == 'gzip':
                self._recv_data = GzipFile('', 'rb', 9, StringIO(self._recv_data)).read().decode('utf-8')
            self.factory.emit('data-received', self._recv_data)
            self._recv_data = ''.encode('utf-8')
            self._header = ''.encode('utf-8')
            self.content_encoding = ''.encode('utf-8')
            self.content_size = 0
        elif added_size > 0:
            self.factory.emit('data-receiving', added_size, self.content_size - len(self._recv_data))

    '''def dataReceived(self, data):
        #debug(DEBUG, 'dataReceived: %s', len(data))
        if data.startswith('HTTP/1.1 404'):
            debug(DEBUG, '%s error 404', self)
            self.factory.emit('error', 'HTTP/1.1 404 response')
            self.transport.loseConnection()
            return
        elif data.startswith('HTTP/1.1 200 OK'):
            self._recv_data = data
        elif self._recv_data:
            self._recv_data += data
        self.factory.emit('on-receiving', data)
        # handle response
        if not self._recv_data:
            return
        try:
            header, data = self._recv_data.split('\r\n\r\n', 1)
        except ValueError:
            return
        content_size, content_encoding = 0, ''
        for h in header.split('\r\n'):
            if h.startswith('Content-Length: '):
                content_size = int(h.replace('Content-Length: ', '').strip())
            elif h.startswith('Content-Size: '):
                content_size = int(h.replace('Content-Size: ', '').strip())
            elif h.startswith('Content-Encoding: '):
                content_encoding = h.replace('Content-Encoding: ', '').strip()
            #elif h.startswith('X-Cache:'):
            #    print h.replace('X-Cache: ', '')
        if content_size == len(data):
            if content_encoding == 'gzip':
                data = GzipFile('', 'rb', 9, StringIO(data)).read()
            self.factory.emit('data-received', data)
            self._recv_data = '''''

    def connectionLost(self, reason):
        debug(DEBUG+1, '%s connectionLost: %s', self, reason)
        del(self._recv_data)
        self._recv_data = ''.encode('utf-8')
        self._close_socket()
        self.factory.emit('connection-lost')

    def _close_socket(self):
        if not self.transport:
            return
        self.transport.loseConnection()
        try:
            self.transport.getHandle().close()
        except Exception as e:
            pass
        # remove internal buffers
        self.transport._tempDataBuffer[:] = ''
        self.transport.dataBuffer = ''
        self.transport = None

class ClientFactory(ClientFactory, gobject.GObject):
    protocol = ClientProtocol
    noisy = False

    __gsignals__ = {
        'connection-made': (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE, #return
            (
                 gobject.TYPE_PYOBJECT, #data
            ) # args
        ),
        'error': (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE, #return
            (str, ) # args
        ),
        'connection-lost': (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE, #return
            () # args
        ),
        'data-received': (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE, #return
            (
                gobject.TYPE_PYOBJECT, #data
            ) # args
        ),
        'data-receiving': (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE, #return
            (
                int, #data diff received
                int, #remaining data size
            ) # args
        ),
        'url-redirect': (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE, #return
            (
                gobject.TYPE_PYOBJECT, #url
            ) # args
        ),
    }

    def __init__(self, url, redirect=False):
        gobject.GObject.__init__(self)
        #
        debug(DEBUG+1, '%s init %s', self, url)
        self.url = url
        self.host, self.port, self.path = parse_url(url)
        self.client = None
        self.connector = reactor.connectTCP(self.host, self.port, self)
        self.redirect = redirect

    def connectionMade(self, host):
        self.client = self.connector.transport.protocol
        self.emit('connection-made', host)

    def makeRequest(self, path, byterange=''):
        self.client.makeRequest(path, byterange)

    def stopFactory(self):
        self.stop()

    def stop(self):
        debug(DEBUG+1, '%s stop', self)
        self.host, self.port = None, 0
        if self.connector:
            self.connector.disconnect()
            self.connector = None
            self.client = None
        gc.collect()

'''
class ConnectionsPool(object):
    def __init__(self):
        self._connections = dict()

    def addConnection(self, url, redirect=False):
        host, port, path = parse_url(url)
        c = self.getConnection(host, port)
        in_pool = False
        if not c:
            # Already in the pool
            c = ClientFactory(url, redirect)
        else:
            c.stop()
            in_pool = True

        c.connect('connection-made', self._onConnectionMade)
        c.connect('connection-lost', self._onConnectionLost)
        c.connect('data-received', self._onDataReceived)
        c.connect('data-receiving', self._onDataReceiving)
        c.connect('url-redirect', self._urlRedirect)


        key = self.connectionKey(connection)
        if not key in self._connections.keys():
            self._connections[key] = connection

    def getConnection(self, host, port):
        key = str(host) + ':' + str(port)
        if key in self._connections.keys():
            return self.connections[key]
        return None

    def removeConnection(self, host, port):
        key = str(host) + ':' + str(port)
        if key in self._connections.keys():
            del self.connections[key]
            return True
        else:
            return False

    def makeRequest(self, url, byterange=''):



    def connectionKey(self, connection):
        return str(connection.host) + ':' + str(connection.port)
'''
def parse_url(url):
    _,_, address, path = url.split('/', 3)
    try:
        host, port = address.split(':', 1)
    except ValueError as e:
        host = address
        port = 80
    port = int(port)
    return host, port, '/'+path

if __name__ == '__main__':
    host, port, path = parse_url('http://193.204.59.68:81/test/0ccf2c94c951880cd2456f4fb2db2b9d/4_ts.m3u8')
    def on_connection(c):
        print(c)
        c.makeRequest(path)
    def on_data(c, data):
        print(c, len(data))
        reactor.callLater(1, c.makeRequest, '/test/0ccf2c94c951880cd2456f4fb2db2b9d/4_00000.ts')
    c = ClientFactory(host, port)
    c.connect('connection-made', on_connection)
    c.connect('data-received', on_data)
    reactor.run()




