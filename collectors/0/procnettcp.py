#!/usr/bin/python
# This file is part of tcollector.
# Copyright (C) 2010  StumbleUpon, Inc.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.  This program is distributed in the hope that it
# will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty
# of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Lesser
# General Public License for more details.  You should have received a copy
# of the GNU Lesser General Public License along with this program.  If not,
# see <http://www.gnu.org/licenses/>.
#
# import TCP socket info into TSDB
#
# Read /proc/net/tcp, which gives netstat -a type
# data for all TCP sockets.

# Note this collector generates a lot of lines, given that there are
#  lots of tcp states and given the number of subcollections we do.
#  We rely heavily on tcollector's deduping.  We could be lazy and
#  just output values only for which we have data, except if we do
#  this then any counters for which we had data would never reach
#  zero since our state machine never enters this condition.

# Metric: proc.net.tcp

# For each run, we classify each connection and generate subtotals.
#   TSD will automatically total these up when displaying
#   the graph, but you can drill down for each possible total or a
#   particular one.  This does generate a large amount of datapoints,
#   as the number of points is (S*(U+1)*V) (currently ~400), where
#   S=number of TCP states, U=Number of users to track, and
#   V=number of services (collections of ports)
# The deduper does dedup this down very well, as only 3 of the 10
# TCP states are generally ever seen, and most servers only run one
# service under one user.  On a typical server this dedups down to
# under 10 values per interval.

# Each connection is broken down with a tag for user=username (see
#   "users" list below) or put under "other" if not in the list.
#   Expand this for any users you care about.
# It is also broken down for each state (state=).
# It is also broken down into services (collections of ports)

# Note that once a connection is closed, Linux seems to forget who
# opened/handled the connection.  For connections in time_wait, for
# example, they will always show user=root.

import os
import sys
import time
import socket
import pwd

users = ("root", "www-data", "mysql")

# Note if a service runs on multiple ports and you
# want to collectively map them up to a single service,
# just give them the same name below

ports = { 80: "http",
          443: "https",
          3001: "http-varnish",
          3002: "http-varnish",
          3003: "http-varnish",
          3004: "http-varnish",
          3005: "http-varnish",
          3006: "http-varnish",
          3007: "http-varnish",
          3008: "http-varnish",
          3009: "http-varnish",
          3010: "http-varnish",
          3011: "http-varnish",
          3012: "http-varnish",
          3013: "http-varnish",
          3014: "http-varnish",
          3306: "mysql",
          3564: "mysql",
          9000: "namenode",
          9090: "thriftserver",
          11211: "memcache",
          11212: "memcache",
          11213: "memcache",
          11214: "memcache",
          11215: "memcache",
          11216: "memcache",
          11217: "memcache",
          11218: "memcache",
          11219: "memcache",
          11220: "memcache",
          11221: "memcache",
          11222: "memcache",
          11223: "memcache",
          11224: "memcache",
          11225: "memcache",
          11226: "memcache",
          50020: "datanode",
          60020: "hregionserver",
        }

services = tuple(set(ports.itervalues()))


tcpstate = { "01": "established",
             "02": "syn_sent",
             "03": "syn_recv",
             "04": "fin_wait1",
             "05": "fin_wait2",
             "06": "time_wait",
             "07": "close",
             "08": "close_wait",
             "09": "last_ack",
             "0A": "listen",
             "0B": "closing",
            }


def isPublicIP(ipstr):
    """
    Take a /proc/net/tcp encoded src or dest string
    Return True if it is coming from public IP space
    (i.e. is not RFC1918, loopback, or broadcast).
    This string is the hex ip:port of the connection.
    (ip is reversed)
    """
    ip, port = ipstr.split(":")
    ip = int(ip, 16)
    byte1 = ip & 0xFF
    byte2 = (ip >> 8) & 0xFF
    if byte1 in (10, 0, 127):
        return False
    if byte1 == 172 and byte2 > 16:
        return False
    if byte1 == 192 and byte2 == 168:
        return False
    return True


def main():
    interval = 60

    ts = int(time.time())

    # resolve the list of users to match on into UIDs
    uids = {}
    for user in users:
        try:
            uids[str(pwd.getpwnam(user)[2])] = user
        except KeyError:
            continue

    while True:
        tcpcounter = {}

        # if IPv6 is enabled, even IPv4 connections will also
        # appear in tcp6. It has the same format, apart from the
        # address size
        for file in ("/proc/net/tcp", "/proc/net/tcp6"):
            f = open(file)
            for line in f:
                try:
                    (num, src, dst, st, queue, when, retrans,
                     uid, timeout, inode) = line.split(None, 9)
                except ValueError:  # Malformed line
                    continue

                if num == "sl":  # header
                    continue

                ip, srcport = src.split(":")
                ip, dstport = dst.split(":")
                srcport = int(srcport, 16)
                dstport = int(dstport, 16)
                service = ports.get(srcport, "other")
                service = ports.get(dstport, service)

                if isPublicIP(dst) or isPublicIP(src):
                    endpoint = "external"
                else:
                    endpoint = "internal"


                user = uids.get(uid, "other")

                key = "state=" + tcpstate[st] + " endpoint=" + endpoint + \
                      " service=" + service + " user=" + user
                if key in tcpcounter:
                    tcpcounter[key] += 1
                else:
                    tcpcounter[key] = 1
            f.close()

        # output the counters
        for st in tcpstate.keys():
            for service in services + ("other",):
                for user in users + ("other",):
                    for endpoint in ("internal", "external"):
                        key = ("state=" + tcpstate[st] + " endpoint=" + endpoint
                               + " service=" + service + " user=" + user)
                        if key in tcpcounter:
                            print "proc.net.tcp", ts, tcpcounter[key], key
                        else:
                            print "proc.net.tcp", ts, "0", key

        sys.stdout.flush()
        time.sleep(interval)
        ts = int(time.time())

if __name__ == "__main__":
    main()
