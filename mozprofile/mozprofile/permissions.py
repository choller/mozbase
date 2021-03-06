# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
#
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
#
# The Original Code is Mozprofile.
#
# The Initial Developer of the Original Code is
#   The Mozilla Foundation.
# Portions created by the Initial Developer are Copyright (C) 2011
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#   Joel Maher <joel.maher@gmail.com>
#
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
#
# ***** END LICENSE BLOCK *****


"""
add permissions to the profile
"""

__all__ = ['MissingPrimaryLocationError', 'MultiplePrimaryLocationsError',
           'DuplicateLocationError', 'BadPortLocationError',
           'LocationsSyntaxError', 'Location', 'ServerLocations',
           'Permissions']

import codecs
import itertools
import os
try:
    import sqlite3
except ImportError:
    from pysqlite2 import dbapi2 as sqlite3
import urlparse


class LocationError(Exception):
    "Signifies an improperly formed location."

    def __str__(self):
        s = "Bad location"
        if self.message:
            s += ": %s" % self.message
        return s


class MissingPrimaryLocationError(LocationError):
    "No primary location defined in locations file."

    def __init__(self):
        LocationError.__init__(self, "missing primary location")


class MultiplePrimaryLocationsError(LocationError):
    "More than one primary location defined."

    def __init__(self):
        LocationError.__init__(self, "multiple primary locations")


class DuplicateLocationError(LocationError):
    "Same location defined twice."

    def __init__(self, url):
        LocationError.__init__(self, "duplicate location: %s" % url)


class BadPortLocationError(LocationError):
    "Location has invalid port value."

    def __init__(self, given_port):
        LocationError.__init__(self, "bad value for port: %s" % given_port)
        

class LocationsSyntaxError(Exception):
    "Signifies a syntax error on a particular line in server-locations.txt."

    def __init__(self, lineno, err=None):
        self.err = err
        self.lineno = lineno

    def __str__(self):
        s = "Syntax error on line %s" % self.lineno
        if self.err:
            s += ": %s." % self.err
        else:
            s += "."
        return s


class Location(object):
    "Represents a location line in server-locations.txt."

    attrs = ('scheme', 'host', 'port')

    def __init__(self, scheme, host, port, options):
        for attr in self.attrs:
            setattr(self, attr, locals()[attr])
        self.options = options
        try:
            int(self.port)
        except ValueError:
            raise BadPortLocationError(self.port)

    def isEqual(self, location):
        "compare scheme://host:port, but ignore options"
        return len([i for i in self.attrs if getattr(self, i) == getattr(location, i)]) == len(self.attrs)

    __eq__ = isEqual

    def url(self):
        return '%s://%s:%s' % (self.scheme, self.host, self.port)

    def __str__(self):
        return  '%s  %s' % (self.url(), ','.join(self.options))


class ServerLocations(object):
    """Iterable collection of locations.
    Use provided functions to add new locations, rather that manipulating
    _locations directly, in order to check for errors and to ensure the
    callback is called, if given.
    """

    def __init__(self, filename=None, add_callback=None):
        self.add_callback = add_callback
        self._locations = []
        self.hasPrimary = False
        if filename:
            self.read(filename)

    def __iter__(self):
        return self._locations.__iter__()

    def __len__(self):
        return len(self._locations)

    def add(self, location, suppress_callback=False):
        if "primary" in location.options:
            if self.hasPrimary:
                raise MultiplePrimaryLocationsError()
            self.hasPrimary = True
        for loc in self._locations:
            if loc.isEqual(location):
                raise DuplicateLocationError(location.url())
        self._locations.append(location)
        if self.add_callback and not suppress_callback:
            self.add_callback([location])

    def add_host(self, host, port='80', scheme='http', options='privileged'):
        if isinstance(options, basestring):
            options = options.split(',')
        self.add(Location(scheme, host, port, options))

    def read(self, filename, check_for_primary=True):
        """
        Reads the file (in the format of server-locations.txt) and add all
        valid locations to the self._locations array.

        If check_for_primary is True, a MissingPrimaryLocationError
        exception is raised if no primary is found.

        This format:
        http://mxr.mozilla.org/mozilla-central/source/build/pgo/server-locations.txt
        The only exception is that the port, if not defined, defaults to 80.

        FIXME: Shouldn't this default to the protocol-appropriate port?  Is
        there any reason to have defaults at all?
        """

        locationFile = codecs.open(filename, "r", "UTF-8")
        lineno = 0
        new_locations = []

        for line in locationFile:
            line = line.strip()
            lineno += 1

            # check for comments and blank lines
            if line.startswith("#") or not line:
                continue

            # split the server from the options
            try:
                server, options = line.rsplit(None, 1)
                options = options.split(',')
            except ValueError:
                server = line
                options = []

            # parse the server url
            if '://' not in server:
                server = 'http://' + server
            scheme, netloc, path, query, fragment = urlparse.urlsplit(server)
            # get the host and port
            try:
                host, port = netloc.rsplit(':', 1)
            except ValueError:
                host = netloc
                port = '80'

            try:
                location = Location(scheme, host, port, options)
                self.add(location, suppress_callback=True)
            except LocationError, e:
                raise LocationsSyntaxError(lineno, e)

            new_locations.append(location)

        # ensure that a primary is found
        if check_for_primary and not self.hasPrimary:
            raise LocationsSyntaxError(lineno + 1,
                                       MissingPrimaryLocationError())

        if self.add_callback:
            self.add_callback(new_locations)


class Permissions(object):
    _num_permissions = 0

    def __init__(self, profileDir, locations=None):
        self._profileDir = profileDir
        self._locations = ServerLocations(add_callback=self.write_db)
        if locations:
            if isinstance(locations, ServerLocations):
                self._locations = locations
                self._locations.add_callback = self.write_db
                self.write_db(self._locations._locations)
            elif isinstance(locations, list):
                for l in locations:
                    self._locations.add_host(**l)
            elif isinstance(locations, dict):
                self._locations.add_host(**locations)
            elif os.path.exists(locations):
                self._locations.read(locations)

    def write_db(self, locations):
        """write permissions to the sqlite database"""

        # Open database and create table
        permDB = sqlite3.connect(os.path.join(self._profileDir, "permissions.sqlite"))
        cursor = permDB.cursor();
        # SQL copied from
        # http://mxr.mozilla.org/mozilla-central/source/extensions/cookie/nsPermissionManager.cpp
        cursor.execute("""CREATE TABLE IF NOT EXISTS moz_hosts (
           id INTEGER PRIMARY KEY,
           host TEXT,
           type TEXT,
           permission INTEGER,
           expireType INTEGER,
           expireTime INTEGER)""")

        for location in locations:
            # set the permissions
            permissions = { 'allowXULXBL': 'noxul' not in location.options }
            for perm, allow in permissions.iteritems():
                self._num_permissions += 1
                if allow:
                    permission_type = 1
                else:
                    permission_type = 2
                cursor.execute("INSERT INTO moz_hosts values(?, ?, ?, ?, 0, 0)",
                               (self._num_permissions, location.host, perm,
                                permission_type))

        # Commit and close
        permDB.commit()
        cursor.close()

    def network_prefs(self, proxy=False):
        """
        take known locations and generate preferences to handle permissions and proxy
        returns a tuple of prefs, user_prefs
        """

        # Grant God-power to all the privileged servers on which tests run.
        prefs = []
        privileged = [i for i in self._locations if "privileged" in i.options]
        for (i, l) in itertools.izip(itertools.count(1), privileged):
            prefs.append(("capability.principal.codebase.p%s.granted" % i, "UniversalPreferencesWrite UniversalXPConnect UniversalPreferencesRead"))

            # TODO: do we need the port?
            prefs.append(("capability.principal.codebase.p%s.id" % i, l.scheme + "://" + l.host))
            prefs.append(("capability.principal.codebase.p%s.subjectName" % i, ""))

        if proxy:
            user_prefs = self.pac_prefs()
        else:
            user_prefs = []

        return prefs, user_prefs

    def pac_prefs(self):
        """
        return preferences for Proxy Auto Config. originally taken from
        http://mxr.mozilla.org/mozilla-central/source/build/automation.py.in
        """

        prefs = []

        # We need to proxy every server but the primary one.
        origins = ["'%s'" % l.url()
                   for l in self._locations
                   if "primary" not in l.options]
        origins = ", ".join(origins)

        # TODO: this is not a reliable way to determine the Proxy host
        for l in self._locations:
            if "primary" in l.options:
                webServer = l.host
                httpPort  = l.port
                sslPort   = 443

        # TODO: this should live in a template!
        pacURL = """data:text/plain,
function FindProxyForURL(url, host)
{
  var origins = [%(origins)s];
  var regex = new RegExp('^([a-z][-a-z0-9+.]*)' +
                         '://' +
                         '(?:[^/@]*@)?' +
                         '(.*?)' +
                         '(?::(\\\\\\\\d+))?/');
  var matches = regex.exec(url);
  if (!matches)
    return 'DIRECT';
  var isHttp = matches[1] == 'http';
  var isHttps = matches[1] == 'https';
  var isWebSocket = matches[1] == 'ws';
  var isWebSocketSSL = matches[1] == 'wss';
  if (!matches[3])
  {
    if (isHttp | isWebSocket) matches[3] = '80';
    if (isHttps | isWebSocketSSL) matches[3] = '443';
  }
  if (isWebSocket)
    matches[1] = 'http';
  if (isWebSocketSSL)
    matches[1] = 'https';

  var origin = matches[1] + '://' + matches[2] + ':' + matches[3];
  if (origins.indexOf(origin) < 0)
    return 'DIRECT';
  if (isHttp)
    return 'PROXY %(remote)s:%(httpport)s';
  if (isHttps || isWebSocket || isWebSocketSSL)
    return 'PROXY %(remote)s:%(sslport)s';
  return 'DIRECT';
}""" % { "origins": origins,
         "remote":  webServer,
         "httpport":httpPort,
         "sslport": sslPort }
        pacURL = "".join(pacURL.splitlines())

        prefs.append(("network.proxy.type", 2))
        prefs.append(("network.proxy.autoconfig_url", pacURL))

        return prefs

    def clean_db(self):
        """Removed permissions added by mozprofile."""

        # Open database and create table
        permDB = sqlite3.connect(os.path.join(self._profileDir, "permissions.sqlite"))
        cursor = permDB.cursor();

        # TODO: only delete values that we add, this would require sending in the full permissions object
        cursor.execute("DROP TABLE IF EXISTS moz_hosts");

        # Commit and close
        permDB.commit()
        cursor.close()
