#!/usr/bin/python
import argparse
import ConfigParser
import md5
import os
import re
import sha
import shutil
import StringIO
import simplejson
import time

from sys import stderr
from pdfminer.pdfinterp import PDFResourceManager, process_pdf
from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams

parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument('-c', '--config',
                    help="Configuration file",
                    default="~/.reportparser.conf",
                    type=str)
parser.add_argument('-d', '--disable-mongo',
                    help="Do not store in MongoDB",
                    action="store_true")

parser.add_argument('report', nargs='+', help="PDF reports to parse")

args = parser.parse_args()

find_ip4 = re.compile(r"\b((?:\d{1,3}\.){3}\d{1,3})")
hashmatch = re.compile(r"\b([a-fA-F0-9]{128}|[a-fA-F0-9]{32}|[a-fA-F0-9]{40})\b")
cvematch = re.compile(r"CVE-\d{4}-\d+\b", re.I)
try:
    config = ConfigParser.ConfigParser()
    config.readfp(open(os.path.expanduser(args.config)))
except IOError, err:
    print >> stderr, "Could not open ~/.reportparser.conf:", err.strerror
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
        f = open(filename, "rb")
        destination_file = "{}/{}.pdf".format(config.get("reportparser", "storage"), produce_sha1(filename))
        shutil.copyfile(filename, destination_file)
        return True
    except (shutil.Error, IOError), err:
        print >> stderr, "Could not store {} to {}: {}".format(filename, config.get("reportparser", "storage"), err.strerror)
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

    device = TextConverter(rsrcmgr, outfp, codec=codec, laparams=LAParams())

    process_pdf(rsrcmgr, device, fp, pagenos, maxpages=maxpages,
                password=password, caching=caching, check_extractable=True)

    result['content'] = {}
    result['content']['hash'] = []
    result['content']['ipv4'] = []
    result['content']['cve'] = []

    for x in hashmatch.findall(output.getvalue()):
        if x in result['content']['hash']:
            continue
        result['content']['hash'].append(x.lower())

    for x in find_ip4.findall(output.getvalue()):
        if x in result['content']['ipv4']:
            continue
        result['content']['ipv4'].append(x)

    for x in cvematch.findall(output.getvalue()):
        if x in result['content']['cve']:
            continue
        result['content']['cve'].append(x)

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
    from pymongo import MongoClient
    connection = MongoClient(config.get("db", "mongohost"))
    inteldb = connection.intel
    result['_id'] = result.pop('id')
    inteldb.reports.save(result)
    connection.close()

if __name__ == '__main__':
    for filename in args.report:
        try:
            fp = file(filename, "rb")
        except IOError, err:
            print >> stderr, "File not found."
            exit(1)

        result = process(filename)
        if not args.disable_mongo:
            store(result)

        print simplejson.dumps(result, sort_keys=True, indent=4)
