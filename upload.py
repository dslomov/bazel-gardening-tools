#!/usr/bin/env python3
"""Upload to database.

Should eventually be combined with categorize tool.

"""


import collections
import sys

import cloudsql


DownloadSample = collections.namedtuple(
    'DownloadSample',
    'file ymd hhmm downloads downloads_sha downloads_sig'
    ' product version arch os extension installer')


def NoneToNull(s):
  if s == 'None':
    return ''
  return s


def upload_file(file, connection):
  with open(file, 'r') as inp:
    print('uploading:', file)
    with connection.cursor() as cursor:
      for line in inp:
        # file| ymd | hm | count | #sha | #sig | product | version | arch | os
        #     extension
        parts = line.strip().split('|')
        sample = DownloadSample(
            file=parts[0],
            ymd=parts[1],
            hhmm=parts[2],
            downloads=parts[3],
            downloads_sha=parts[4],
            downloads_sig=parts[5],
            product=parts[6],
            version=NoneToNull(parts[7]),
            arch=NoneToNull(parts[8]),
            os=NoneToNull(parts[9]),
            extension=NoneToNull(parts[10]),
            installer=parts[11] == 'installer')

        cmd = """INSERT INTO gh_downloads(
            sample_date, filename, downloads_total, sha256_total, sig_total,
            product, version, arch, os, extension, is_installer,
            downloads, sha256, sig)
        VALUES(
            '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%d',
            0, 0, 0
        )""" % (sample.ymd, sample.file,
                sample.downloads, sample.downloads_sha, sample.downloads_sig,
                sample.product, sample.version, sample.arch, sample.os,
                sample.extension, 1 if sample.installer else 0)
        cursor.execute(cmd)
    connection.commit()


def main(args):
  connection = cloudsql.Connect('metrics')
  for file in args:
    upload_file(file, connection)
  connection.close()


if __name__ == '__main__':
  main(sys.argv[1:])
