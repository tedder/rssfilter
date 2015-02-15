#!/usr/bin/python

import re
import json
import requests
import speedparser
import yaml
import calendar
import time
import PyRSS2Gen
import StringIO

dthandler = lambda obj: calendar.timegm(obj) if isinstance(obj, time.struct_time) else json.JSONEncoder().default(obj)

def do_feed(config):
  req = requests.get(config['url'])
  #print req.text
  feed = speedparser.parse(req.content, clean_html=True) #, encoding='UTF-8')
  #print "feed: %s" % json.dumps(feed, default=dthandler, indent=2)
  #feed['feed']['entries']
  #title, summary, content
  #print str(*feed)
  rss = PyRSS2Gen.RSS2(
    title = feed['feed'].get('title'),
    link = feed['feed'].get('link'),
    description = feed['feed'].get('description'),
    pubDate = feed['feed'].get('pubDate'),
    lastBuildDate = feed['feed'].get('lastBuildDate'),
    categories = feed['feed'].get('categories'),
    ttl = feed['feed'].get('ttl'),
    image = feed['feed'].get('image'),
  )

  #print json.dumps(feed)
  print config['filter']
  entries = feed['entries']
  for filterset in config['filter']:
    filter_type, filter_rules = filterset.popitem()
    print "start entry count: %g" % len(entries)
    if filter_type == 'include':
      entries = filter_include(entries, filter_rules)
    elif filter_type == 'exclude':
      entries = filter_exclude(entries, filter_rules)
    else:
      raise "can only handle include/exclude filter types. being asked to process %s" % filter_type
    print "  end entry count: %g" % len(entries)
    #print "filter_set: %s / %s" % (filter_type, filter_rules)

  print "final entry count: %g" % len(entries)

  rssfile = StringIO.StringIO()
  rss.write_xml(rssfile)
  rssfile.seek(0)
  #print rssfile.read()

def stringify(blob):
  retstr = ''
  if isinstance(blob, list):
    for e in blob:
      retstr += stringify(e)
  elif isinstance(blob, dict):
    for k,v in blob.iteritems():
      retstr += stringify(k)
      retstr += stringify(v)
  elif isinstance(blob, str):
    retstr += blob
  elif isinstance(blob, unicode):
    retstr += blob.encode('utf8')
  else:
    raise "unknown type: %s" % type(blob)
  return retstr

def rule_matches(entry, rule):
  # content can be a list/dict/etc, so it needs some help.
  contentstr = stringify(entry.get('content')).lower()
  titlestr = entry.get('title', '').lower()
  summarystr = entry.get('summary', '').lower()
  linkstr = entry.get('link', '').lower()
  #print "content: %s" % contentstr
  if rule[0] == '/':
    # regex. trim off leading/trailing /slash/
    rex = rule.strip('/')
    if re.search(rex, titlestr) or re.search(rex, summarystr) or re.search(rex, contentstr) or re.search(rex, linkstr):
      return True
  elif rule in titlestr or rule in summarystr or rule in contentstr or rule in linkstr:
    return True
  return False

def item_matches(entry, rules):
  for rule in rules:
    if rule_matches(entry, rule):
      return True
  return False

def filter_include(entries, rules):
  # only include items that match. all others will be removed.
  print "hello include"
  newlist = []
  for entry in entries:
    if item_matches(entry, rules):
      print "entry: %s" % entry
      newlist.append(entry)
  return newlist

def filter_exclude(entries, rules):
  # include all items unless they match.
  print "hello exclude"
  newlist = []
  for entry in entries:
    #print "entry: %s" % entry
    if not item_matches(entry, rules):
      newlist.append(entry)
  return newlist

with open("test.yml", "r") as f:
  config = yaml.load(f)

print config
for feedcfg in config:
  do_feed(feedcfg)


