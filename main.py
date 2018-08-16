#!/usr/bin/env python2
# coding:utf-8

from __future__ import unicode_literals
import re
import boto3
import requests
import speedparser
import yaml
import ssl
import PyRSS2Gen
import HTMLParser
from io import BytesIO

# py3 doesn't have a unicode type or method, which makes it difficult to write
# unicode-variable-containing code that is compatible with both. Finally found
# this: http://python-future.org/compatible_idioms.html#unicode
from builtins import str as unicode

S3_OUTPUT_BUCKET = 'dyn.tedder.me'
S3_OUTPUT_PREFIX = 'rss_filter/'

#dthandler = lambda obj: calendar.timegm(obj) if isinstance(obj, time.struct_time) else json.JSONEncoder().default(obj)

def do_feed(config):
  try:
    req = requests.get(config['url'])
    #print(req.content)
  except requests.exceptions.ConnectionError:
    if 'baconbits' not in config['url']:
      print("URL connection fail: " + config['url'])
    return
  except ssl.SSLError:
    print("SSL URL connection fail: " + config['url'])
    return
  feed = speedparser.parse(req.content, clean_html=True, encoding='UTF-8')

  entries = feed['entries']
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

  pars = HTMLParser.HTMLParser()

  items = []
  # convert the entries to RSSItems, build the list we'll stick in the RSS..
  for entry in entries:
    #print(pars.unescape(entry.get('title', '').encode('utf-8')))
    item = PyRSS2Gen.RSSItem(
      title = pars.unescape(entry.get('title', '')),
      link = pars.unescape(entry.get('link', '')),
      description = pars.unescape(entry.get('description', '')),
      author = pars.unescape(entry.get('author', '')),
      categories = entry.get('categories'),
      comments = pars.unescape(entry.get('comments', '')),
      enclosure = entry.get('enclosure'),
      guid = entry.get('guid'),
      pubDate = entry.get('pubDate'),
      source = entry.get('source'),
    )
    items.append(item)

  #print("xx", pars.unescape(feed['feed'].get('title', '')))
  #print(pars.unescape(feed['feed'].get('link', '')))
  #print(config['output'])
  rss = PyRSS2Gen.RSS2(
    title = pars.unescape(feed['feed'].get('title', '')),
    link = pars.unescape(feed['feed'].get('link', '')),
    description = pars.unescape(feed['feed'].get('description', '')),
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
      xform_type, xform_find, xform_replace = rule
      if xform_type == 'regex_link':
        entry['link'] = re.sub(xform_find, xform_replace, entry['link'])
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
      rssfile = do_feed(feedcfg)
      if not rssfile: continue
      dest = S3_OUTPUT_PREFIX + feedcfg['output']
      s3.put_object(Bucket=S3_OUTPUT_BUCKET, Key=dest, Body=rssfile, ContentType='application/rss+xml', CacheControl='max-age=1800,public', ACL='public-read')
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
    config_file = requests.get(url).text
  elif filename:
    with open(filename) as f:
      config_file = f.read()
  else:
    raise "need s3 or http details for config"

  config = yaml.load(config_file)
  #print(config)
  do_config(config)


s3 = boto3.client('s3', region_name='us-west-2')
read_config(s3, 'tedder', 'rss/main_list.yml')

