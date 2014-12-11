#!/usr/bin/python
from pdfminer.pdfinterp import PDFResourceManager, process_pdf
from pdfminer.converter import TextConverter

import os
import sys
import StringIO
import time
import re
import simplejson
import md5
import sha
import pymongo
import ConfigParser

find_ip4 = re.compile(r"\b((?:\d{1,3}\.){3}\d{1,3})") 
hashmatch = re.compile(r"\b([a-zA-Z0-9]{128}|[a-zA-Z0-9]{32}|[a-zA-Z0-9]{40})\b")

try:
    config = ConfigParser.ConfigParser()
    config.readfp(open(os.path.expanduser("~/.reportparser.conf")))
except:
    print >> sys.stderr, "File ~/.reportparser.conf not found."
    from sys import exit
    exit(1)

def produce_md5(filename):
    f = file(filename, "rb")
    q = md5.new(f.read())
    return q.hexdigest()

def produce_sha1(filename):
    f = file(filename, "rb")
    q = sha.sha(f.read())
    return q.hexdigest()

def save_to_storage(filename):
    try:
        f = file(filename, "rb")
        output = file("%s/%s.pdf" % (config.get("reportparser", "storage"), produce_sha1(filename)), "w")
        output.write(f.read())
        f.close()
        output.close()
        return True
    except:
        return False

def process(filename):
    result = {}
    output = StringIO.StringIO()
    caching = True
    
    pagenos = set()
    rsrcmgr = PDFResourceManager(caching=caching)
    
    outfp = output
    maxpages = 0
    password = ""
    codec = "utf-8"
    
    device = TextConverter(rsrcmgr, outfp, codec=codec)
    
    process_pdf(rsrcmgr, device, fp, pagenos, maxpages=maxpages, password=password,
                        caching=caching, check_extractable=True)
    
    
    result['content'] = {}
    result['content']['hash'] = []
    result['content']['ipv4'] = []
    
    for x in hashmatch.findall(output.getvalue()):
        if x in result['content']['hash']:
            continue
        result['content']['hash'].append(x.lower())
    
    for x in find_ip4.findall(output.getvalue()):
        if x in result['content']['ipv4']:
            continue
        result['content']['ipv4'].append(x)
    
    
    result['file'] = {}
    result['file']['parsed'] = time.time()
    result['file']['name'] = filename.split("/")[-1]
    result['file']['hash'] = {}
    result['file']['hash']['md5'] = produce_md5(filename)
    result['file']['hash']['sha1'] = produce_sha1(filename)
    result['file']['saved'] = save_to_storage(filename)
    
    result['content']['hash'].sort()
    result['content']['ipv4'].sort()
    
    result['id'] = result['file']['hash']['sha1']
    
    output.close()

    return result

def store(result):
    connection = pymongo.Connection(host=config.get("db", "mongohost"))
    inteldb = connection.intel
    result['_id'] = result.pop('id')
    inteldb.reports.save(result)
    connection.close()

if __name__ == '__main__':
    if not len(sys.argv) == 2:
        print >> sys.stderr, "Provide a file."
        sys.exit(1)
    try:
        filename = sys.argv[1]
        fp = file(filename, "rb")
    except:
        print >> sys.stderr, "File not found."
        sys.exit(1)
    
    result = process(filename) 
    store(result)

    print simplejson.dumps(result, sort_keys=True, indent=4)

