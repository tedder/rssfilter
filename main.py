#!/usr/bin/env python3
# coding:utf-8

from __future__ import unicode_literals
import re
import boto3
import requests
import speedparser
import yaml
import ssl
import sys
import PyRSS2Gen
import html
from html.parser import HTMLParser
from io import BytesIO

# py3 doesn't have a unicode type or method, which makes it difficult to write
# unicode-variable-containing code that is compatible with both. Finally found
# this: http://python-future.org/compatible_idioms.html#unicode
from builtins import str as unicode

DEBUG = 0
if len(sys.argv) > 1 and sys.argv[1] == 'debug':
  DEBUG = 1

S3_OUTPUT_BUCKET = 'dyn.tedder.me'
S3_OUTPUT_PREFIX = 'rss_filter/'

session = requests.Session()
session.headers.update({'User-Agent': 'RSS Filter; ideal.sand3129@notmyna.me'})

#dthandler = lambda obj: calendar.timegm(obj) if isinstance(obj, time.struct_time) else json.JSONEncoder().default(obj)

def do_feed(config):
  try:
    if DEBUG: print("pulling url: {}".format(config['url']))
    req = session.get(config['url'], timeout=20)
    if DEBUG: print("pulled")
    #print(req.content)
  except requests.exceptions.ReadTimeout:
    if 'bitmetv' not in config['url'] and 'portlandtribune' not in config['url']:
      print("URL timeout: " + config['url'])
    return
  except requests.exceptions.ConnectionError:
    if 'baconbits' not in config['url']:
      print("URL connection fail: " + config['url'])
    return
  except ssl.SSLError:
    print("SSL URL connection fail: " + config['url'])
    return
  content = req.content #.decode('utf-8')
  print(content)
  if DEBUG: print("url content length: ", len(content))
  feed = speedparser.parse(content, clean_html=True, encoding='UTF-8')

  print(f"keys: {feed.keys()} {len(feed['feed'])}")
  print(f"{feed['bozo']} // {feed.get('bozo_exception')} {feed.get('bozo_tb')}")
  entries = feed['entries']
  print(f"entries: {len(entries)}")
  #print("entries: " + str(entries)[:100])
  for filterset in config.get('filter', []):
    filter_type, filter_rules = filterset.popitem()
    if filter_type == 'include':
      entries = filter_include(entries, filter_rules)
    elif filter_type == 'exclude':
      entries = filter_exclude(entries, filter_rules)
    elif filter_type == 'transform':
      #print "transforming, rules: " + str(filter_rules)
      #print("transforming, entries: " + str(entries)[:100])
      entries = transform(entries, filter_rules)
    else:
      raise Exception("can only handle include/exclude filter types. being asked to process %s" % filter_type)

  if DEBUG: print(f"done composing, entries: {len(entries)}")
  #pars = HTMLParser()

  items = []
  # convert the entries to RSSItems, build the list we'll stick in the RSS..
  for entry in entries:
    #print(html.unescape(entry.get('title', '').encode('utf-8')))
    item = PyRSS2Gen.RSSItem(
      title = html.unescape(entry.get('title', '')),
      link = html.unescape(entry.get('link', '')),
      description = html.unescape(entry.get('description', '')),
      author = html.unescape(entry.get('author', '')),
      categories = entry.get('categories'),
      comments = html.unescape(entry.get('comments', '')),
      enclosure = entry.get('enclosure'),
      guid = entry.get('guid'),
      pubDate = entry.get('pubDate'),
      source = entry.get('source'),
    )
    items.append(item)
    if DEBUG: print(f"done composing, items: {len(items)}")
  #print("xx", html.unescape(feed['feed'].get('title', '')))
  #print(html.unescape(feed['feed'].get('link', '')))
  #print(config['output'])
  rss = PyRSS2Gen.RSS2(
    title = html.unescape(feed['feed'].get('title', '')),
    link = html.unescape(feed['feed'].get('link', '')),
    description = html.unescape(feed['feed'].get('description', '')),
    pubDate = feed['feed'].get('pubDate'),
    lastBuildDate = feed['feed'].get('lastBuildDate'),
    categories = feed['feed'].get('categories'),
    ttl = feed['feed'].get('ttl'),
    image = feed['feed'].get('image'),
    items = items
  )

  rssfile = BytesIO()
  rss.write_xml(rssfile)
  rssfile.seek(0)
  return rssfile

def safe_unicode(blob):
  return unicode(blob, 'utf8')

def stringify(blob):
  retstr = ''
  if not blob:
    return '' # we were passed nothing, so return nothing
  elif isinstance(blob, list):
    for e in blob:
      retstr += stringify(e)
  elif isinstance(blob, dict):
    for k,v in blob.items():
      retstr += stringify(unicode(k))
      #print(type(retstr), type(v), v)
      retstr += stringify(unicode(v))
  elif isinstance(blob, str):
    retstr += unicode(blob)
  elif isinstance(blob, bytes):
    retstr += unicode(blob)
  elif isinstance(blob, unicode):
    retstr += blob
  else:
    raise Exception("unknown type: %s" % str(type(blob)))

  #print(retstr)
  return retstr

def rule_matches(entry, rule):
  # content can be a list/dict/etc, so it needs some help.
  contentstr = stringify(entry.get('content')).encode('utf-8').lower()
  titlestr = entry.get('title', '').encode('utf-8').lower()
  summarystr = entry.get('summary', '').encode('utf-8').lower()
  linkstr = entry.get('link', '').encode('utf-8').lower()

  #print("title: {}".format(titlestr))
  #print("con: %s".format(contentstr))

  if rule[0] == '/':
    # regex. trim off leading/trailing /slash/
    rex = rule.strip('/')
    if re.search(rex, titlestr) or re.search(rex, summarystr) or re.search(rex, contentstr) or re.search(rex, linkstr):
      return True
  #elif rule in titlestr or rule in summarystr or rule in contentstr or rule in linkstr:
  elif rule in titlestr:
    return True
  elif rule in summarystr:
    return True
  elif rule in contentstr:
    #print(contentstr)
    return True
  elif rule in linkstr:
    return True
  return False

def item_matches(entry, rules):
  for rule in rules:
    if rule_matches(entry, rule.encode('utf-8')):
      #print "rule '%s' matched entry: %s" % (rule.decode('utf-8'), entry.decode('utf-8'))
      return True
  return False

def transform(entries, rules):
  for entry in entries:
    #print(entry)
    for rule in rules:
    #for
      if not rule: break
      (xform_type, xform_find, xform_replace) = [None, None, None]
      if len(rule) == 1:
        (xform_type) = rule
      else:
        (xform_type, xform_find, xform_replace) = rule

      if xform_type == 'regex_link':
        entry['link'] = re.sub(xform_find, xform_replace, entry['link'])
      elif xform_type == 'regex_guid':
        entry['guid'] = re.sub(xform_find, xform_replace, entry['guid'])
      elif xform_type == 'comments_to_link' and entry.get('comments'):
        entry['link'] = entry['comments']
      elif xform_type == 'link_to_description':
        desclink = re.sub(xform_find, xform_replace, entry['link'])
        entry['summary'] += """<p /><a href="%s">description</a>""" % desclink
      elif xform_type == 'description':
        #print("desc: {}".format(entry['description']))
        #print("replacing {} with {}".format(xform_find, xform_replace))
        entry['description'] = re.sub(xform_find, xform_replace, entry['description'])
        #print("output: {}".format(entry['description']))
  return entries

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
  for feedcfg in config:
    # pull off non-feed config entries first.
    if feedcfg.get('include'):
      feedcfg['include']

    try:
      if DEBUG: print("starting config entry")
      rssfile = do_feed(feedcfg)
      if not rssfile: continue
      dest = S3_OUTPUT_PREFIX + feedcfg['output']
      if DEBUG: print("pushing to " + dest)
      #s3.put_object(Bucket=S3_OUTPUT_BUCKET, Key=dest, Body=rssfile, ContentType='application/rss+xml', CacheControl='max-age=1800,public', ACL='public-read')
      s3.put_object(Bucket=S3_OUTPUT_BUCKET, Key=dest, Body=rssfile, ContentType='text/xml', CacheControl='max-age=1800,public', ACL='public-read')
    except requests.exceptions.ConnectionError:
      if 'baconbits' in feedcfg['url']:
        return
      print("failed to get feed: " + feedcfg['url'] + "\n" + str(e))
    except requests.exceptions.ChunkedEncodingError as e:
      print("failed to get feed: " + feedcfg['url'] + "\n" + str(e))

    #print "wrote feed to %s" % dest

def read_config(s3, bucket=None, key=None, url=None, filename=None):
  if bucket and key:
    config_file = s3.get_object(Bucket='tedder', Key='rss/main_list.yml')['Body'].read().decode('utf-8')
    #bucket = s3.get_bucket('tedder')
    #config_file = bucket.get_key('rss/main_list.yml').get_contents_as_string()
  elif url:
    config_file = session.get(url).text
  elif filename:
    with open(filename) as f:
      config_file = f.read()
  else:
    raise "need s3 or http details for config"

  config = yaml.load(config_file, Loader=yaml.FullLoader)
  #print(config)
  if DEBUG: print("haz config")
  return config


s3 = boto3.client('s3', region_name='us-west-2')
conf = read_config(s3, 'tedder', 'rss/main_list.yml')
do_config(conf)

