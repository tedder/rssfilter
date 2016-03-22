#!/usr/bin/python

import re
import json
import boto3
import requests
import speedparser
import yaml
import calendar
import time
import PyRSS2Gen
import StringIO

S3_OUTPUT_BUCKET = 'dyn.tedder.me'
S3_OUTPUT_PREFIX = 'rss_filter/'

#dthandler = lambda obj: calendar.timegm(obj) if isinstance(obj, time.struct_time) else json.JSONEncoder().default(obj)

def do_feed(config):
  try:
    req = requests.get(config['url'])
  except requests.exceptions.ConnectionError:
    if 'baconbits' not in config['url']:
      print("URL connection fail: " + config['url'])
    return
  feed = speedparser.parse(req.content, clean_html=True) #, encoding='UTF-8')

  entries = feed['entries']
  #print "entries: " + str(entries)[:100]
  for filterset in config['filter']:
    filter_type, filter_rules = filterset.popitem()
    if filter_type == 'include':
      entries = filter_include(entries, filter_rules)
    elif filter_type == 'exclude':
      entries = filter_exclude(entries, filter_rules)
    elif filter_type == 'transform':
      #print "transforming, rules: " + str(filter_rules)
      #print "transforming, entries: " + str(entries)[:100]
      entries = transform(entries, filter_rules)
    else:
      raise Exception("can only handle include/exclude filter types. being asked to process %s" % filter_type)

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
  if not blob:
    return retstr
  elif isinstance(blob, list):
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
    raise Exception("unknown type: %s" % str(type(blob)))
  return retstr

def rule_matches(entry, rule):
  # content can be a list/dict/etc, so it needs some help.
  contentstr = stringify(entry.get('content')).lower()
  titlestr = entry.get('title', '').encode('utf-8').lower()
  summarystr = entry.get('summary', '').encode('utf-8').lower()
  linkstr = entry.get('link', '').encode('utf-8').lower()

  #print "title: %s" % titlestr

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
    for rule in rules:
    #for 
      if not rule: break
      xform_type, xform_find, xform_replace = rule
      if xform_type == 'link_to_description':
        desclink = re.sub(xform_find, xform_replace, entry['link'])
        entry['summary'] += """<p /><a href="%s">description</a>""" % desclink
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
      s3.put_object(Bucket=S3_OUTPUT_BUCKET, Key=dest, Body=rssfile, StorageClass='REDUCED_REDUNDANCY', ContentType='application/rss+xml', CacheControl='max-age=600,public', ACL='public-read')
    except requests.exceptions.ConnectionError:
      if 'baconbits' in feedcfg['url']:
        return
      print("failed to get feed: " + feedcfg['url'])
    #print "wrote feed to %s" % dest

def read_config(s3, bucket=None, key=None, url=None):
  if bucket and key:
    config_file = s3.get_object(Bucket='tedder', Key='rss/main_list.yml')['Body'].read().decode('utf-8')
    #bucket = s3.get_bucket('tedder')
    #config_file = bucket.get_key('rss/main_list.yml').get_contents_as_string()
  elif url:
    config_file = requests.get(url).text
  else:
    raise "need s3 or http details for config"

  config = yaml.load(config_file)
  do_config(config)


s3 = boto3.client('s3', region_name='us-west-2')
read_config(s3, 'tedder', 'rss/main_list.yml')

