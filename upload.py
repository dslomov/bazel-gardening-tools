#!/usr/bin/env python3
"""Upload to database.

- takes daily cummulative download counts,
- diffs from previous day
- uploads record with cummulative and daily count
"""

import argparse
import collections
import datetime
import sys

import cloudsql


DownloadSample = collections.namedtuple(
    'DownloadSample',
    'file sample_date product version arch os extension installer'
    ' downloads downloads_total sha256 sha256_total sig sig_total')
DownloadSample.__new__.__defaults__ = (None,) * 14


def NoneToNull(s):
  if s == 'None':
    return ''
  return s


def GatherPreviousDownloads(connection, trailing_days):
  """Get trailing_days worth of download records.

  We work in a 'days from 2019-01-01' system, so that the 'day' of any sample
  is from that rather than a date type.

  Args:
    trailing_days: Number of days to look back in histroy.
  Returns:
    map: (product, filename, version, day) -> DownloadSample
  """
  ret = {}
  max_day = 0
  with connection.cursor() as cursor:
    cursor.execute(
        """
        select product, filename, version, sample_date,
               datediff(sample_date, '2019-01-01') as day,
               downloads, downloads_total,
               sha256, sha256_total,
               sig, sig_total
        from gh_downloads
        where sample_date >= date_sub(curdate(), interval %d day)
        order by product, filename, version, day
        """ % (trailing_days))

    while True:
      try:
        row = cursor.fetchone()
        if not row:
          break
      except Exception as e:
        print(e)
        continue

      if row:
        product = row['product']
        filename = row['filename']
        version = row['version']
        sample_date = row['sample_date']
        day = row['day']
        downloads = row['downloads']
        downloads_total = row['downloads_total']
        sha256 = row['sha256']
        sha256_total = row['sha256_total']
        sig = row['sig']
        sig_total = row['sig_total']
        ret[(product, filename, version, day)] = DownloadSample(
            product=product,
            file=filename,
            version=version,
            sample_date=sample_date,
            downloads= downloads,
            downloads_total=downloads_total,
            sha256=sha256,
            sha256_total=sha256_total,
            sig=sig,
            sig_total=sig_total,
            arch='',
            os='',
            extension='',
            installer='')
        max_day = day if day > max_day else max_day
  print('Maximum day is %d' % max_day)
  return ret


def upload_file(file, history, connection, dry_run=True):
  if not dry_run:
    cursor = connection.cursor()

  epoch = datetime.datetime.strptime('2019-01-01', '%Y-%m-%d')
  with open(file, 'r') as inp:
    print('uploading:', file)
    for line in inp:
      # file| ymd | hm | count | #sha | #sig | product | version | arch | os
      #     extension
      parts = line.strip().split('|')
      sample = DownloadSample(
          file=parts[0],
          sample_date=parts[1],
          downloads_total=int(parts[3]),
          sha256_total=int(parts[4]),
          sig_total=int(parts[5]),
          product=parts[6],
          version=NoneToNull(parts[7]),
          arch=NoneToNull(parts[8]),
          os=NoneToNull(parts[9]),
          extension=NoneToNull(parts[10]),
          installer=parts[11] == 'installer',
          downloads=0,
          sha256=0,
          sig=0)

      sample_day = datetime.datetime.strptime(sample.sample_date, "%Y-%m-%d")
      day = (sample_day - epoch).days

      previous = history.get((sample.product, sample.file, sample.version, day-1))
      downloads = sha256 = sig=0
      if not previous:
        print(sample.product, sample.file, sample.version, sample.sample_date,
              '=No history')
      else:
         downloads = sample.downloads_total - previous.downloads_total
         sha256 = sample.sha256_total - previous.sha256_total
         sig = sample.sig_total - previous.sig_total

         if previous.downloads * 115 // 100 < downloads:
           print(sample.product, sample.file, sample.version, sample.sample_date,
                 downloads, 'Big jump from %d' % previous.downloads)

      cmd = """INSERT INTO gh_downloads(
          sample_date, filename, downloads_total, sha256_total, sig_total,
          product, version, arch, os, extension, is_installer,
          downloads, sha256, sig)
      VALUES(
          '%s', '%s', %d, %d, %d, '%s', '%s', '%s', '%s', '%s', %d,
          %d, %d, %d
      )""" % (sample.sample_date, sample.file,
              sample.downloads_total, sample.sha256_total, sample.sig_total,
              sample.product, sample.version, sample.arch, sample.os,
              sample.extension, 1 if sample.installer else 0,
              downloads, sha256, sig,
              )
      if not dry_run:
        cursor.execute(cmd)
  if not dry_run:
    cursor.close()
    connection.commit()


def main():
  parser = argparse.ArgumentParser(description='Upload categorized download counts')

  parser.add_argument(
        '--database', default='metrics',
        help='Get all repositories rather than just the select ones')
  parser.add_argument(
        '--dry_run', '-n', action='store_true',
        help='Just print updates, do not commit them')
  parser.add_argument(
        '--window', type=int, default=7,
        help='How many days to look back in time')
  parser.add_argument('files', nargs='*')
  options = parser.parse_args()

  connection = cloudsql.Connect(options.database)
  history = GatherPreviousDownloads(connection, options.window)
  for file in options.files:
    upload_file(file, history, connection, options.dry_run)
  connection.close()


if __name__ == '__main__':
  main()
