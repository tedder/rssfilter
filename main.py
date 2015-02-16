#!/usr/bin/python

import re
import json
import boto
import requests
import speedparser
import yaml
import calendar
import time
import PyRSS2Gen
import StringIO

S3_OUTPUT_BUCKET = 'dyn.tedder.me'
S3_OUTPUT_PREFIX = '/rss_filter/'

#dthandler = lambda obj: calendar.timegm(obj) if isinstance(obj, time.struct_time) else json.JSONEncoder().default(obj)

def do_feed(config):
  req = requests.get(config['url'])
  feed = speedparser.parse(req.content, clean_html=True) #, encoding='UTF-8')

  entries = feed['entries']
  for filterset in config['filter']:
    filter_type, filter_rules = filterset.popitem()
    if filter_type == 'include':
      entries = filter_include(entries, filter_rules)
    elif filter_type == 'exclude':
      entries = filter_exclude(entries, filter_rules)
    else:
      raise "can only handle include/exclude filter types. being asked to process %s" % filter_type

  items = []
  # convert the entries to RSSItems, build the list we'll stick in the RSS..
  for entry in entries:
    item = PyRSS2Gen.RSSItem(
      title = entry.get('title'),
      link = entry.get('link'),
      description = entry.get('description'),
      author = entry.get('author'),
      categories = entry.get('categories'),
      comments = entry.get('comments'),
      enclosure = entry.get('enclosure'),
      guid = entry.get('guid'),
      pubDate = entry.get('pubDate'),
      source = entry.get('source'),
    )
    items.append(item)

  rss = PyRSS2Gen.RSS2(
    title = feed['feed'].get('title'),
    link = feed['feed'].get('link'),
    description = feed['feed'].get('description'),
    pubDate = feed['feed'].get('pubDate'),
    lastBuildDate = feed['feed'].get('lastBuildDate'),
    categories = feed['feed'].get('categories'),
    ttl = feed['feed'].get('ttl'),
    image = feed['feed'].get('image'),
    items = items
  )

  rssfile = StringIO.StringIO()
  rss.write_xml(rssfile)
  rssfile.seek(0)
  return rssfile

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
  newlist = []
  for entry in entries:
    if item_matches(entry, rules):
      newlist.append(entry)
  return newlist

def filter_exclude(entries, rules):
  # include all items unless they match.
  newlist = []
  for entry in entries:
    if not item_matches(entry, rules):
      newlist.append(entry)
  return newlist

def do_include(includeurl):
  if includeurl.startswith('http'):
    read_config(s3, url=includeurl)
    
  elif includeurl.startswith('s3'):
    match = re.search('s3://([^\/]+)\/(.+)', includeurl)
    bucket = match.group(0)
    key = match.group(1)
    read_config(s3, bucket=bucket, key=key)
  else:
    raise "did not recognize include url format. either http[s]:// or s3:// please."


def do_config(config):
  rss_bucket = s3.get_bucket(S3_OUTPUT_BUCKET)
  for feedcfg in config:
    # pull off non-feed config entries first.
    if feedcfg.get('include'):
      feedcfg['include']

    rssfile = do_feed(feedcfg)
    dest = S3_OUTPUT_PREFIX + feedcfg['output']
    rss_bucket.new_key(dest).set_contents_from_file(rssfile, reduced_redundancy=True, rewind=True, headers={'Content-Type': 'application/rss+xml', 'Cache-Control':'max-age=600,public'}, policy='public-read')
    print "wrote feed to %s" % dest

def read_config(s3, bucket=None, key=None, url=None):
  if bucket and key:
    bucket = s3.get_bucket('tedder')
    config_file = bucket.get_key('rss/main_list.yml').get_contents_as_string()
  elif url:
    config_file = requests.get(url).text
  else:
    raise "need s3 or http details for config"

  config = yaml.load(config_file)
  do_config(config)


s3 = boto.connect_s3()
read_config(s3, 'tedder', 'rss/main_list.yml')

