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

_EPOCH = datetime.datetime.strptime('2019-01-01', '%Y-%m-%d')
_VERBOSE = False


def none_to_null(s):
  if s == 'None':
    return ''
  return s


def gather_previous_downloads(connection, trailing_days):
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
        """ % (trailing_days))
        # order by product, filename, version, day

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


class DailyCountUploader(object):

  def __init__(self, history, connection, window=1, backfill=True,
               dry_run=True):
    self.history = history
    self.connection = connection
    self.window = window
    self.backfill = backfill
    self.dry_run = dry_run
    self.cursor = None

  def upload_file(self, file):
    if not self.dry_run:
      self.cursor = self.connection.cursor()

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
            version=none_to_null(parts[7]),
            arch=none_to_null(parts[8]),
            os=none_to_null(parts[9]),
            extension=none_to_null(parts[10]),
            installer=parts[11] == 'installer',
            downloads=0,
            sha256=0,
            sig=0)
        self.process_sample(sample)

    if not self.dry_run:
      self.cursor.close()
      self.connection.commit()

  def process_sample(self, sample):
    sample_dt = datetime.datetime.strptime(sample.sample_date, '%Y-%m-%d')
    sample_day = (sample_dt - _EPOCH).days
    downloads = sha256 = sig= 0

    if self.history.get(
        (sample.product, sample.file, sample.version, sample_day)):
      raise Exception('We have already loaded %s %s %s %s' % (
          sample.product, sample.file, sample.version, sample_day))

    previous = None
    previous_day = sample_day
    while not previous and sample_day - previous_day <= self.window:
      previous_day -= 1
      previous = self.history.get(
          (sample.product, sample.file, sample.version, previous_day))

    if not previous:
      print(sample.product, sample.file, sample.version, sample.sample_date,
            '=No history')
    else:
      downloads = sample.downloads_total - previous.downloads_total
      sha256 = sample.sha256_total - previous.sha256_total
      sig = sample.sig_total - previous.sig_total

      fill_days = sample_day - previous_day
      if self.backfill and fill_days > 1:
        # backfill algorithm:
        # - spread delta over all the days to be inserted. this includes
        #   the sample for today
        # - leave any rounding error in the sample for today.
        inc_downloads = downloads // fill_days
        inc_sha256 = sha256 // fill_days
        inc_sig = sig // fill_days

        for day_to_fill in range(previous_day + 1, sample_day):
          filler = self.new_sample(sample, day_to_fill, inc_downloads,
                                   inc_sha256, inc_sig)
          print('backfill: %s %s %s %s' % (
              filler.sample_date, filler.product, filler.version,
              filler.downloads))
          self.add_daily_counts(filler)
          downloads -= inc_downloads
          sha256 -= inc_sha256
          sig -= inc_sig

      # assert: no need to backfill: downloads is what we got today
      # assert: with backfill: downloads holds ~avg/day change over period
      # assert: skip backfill: downloads holds multi-day delta
      if (downloads > 10) and (previous.downloads * 115 // 100 < downloads):
        print(sample.product, sample.file, sample.version,
              sample.sample_date, downloads,
              'large jump from %d' % previous.downloads)

    s = self.new_sample(sample, sample_day, downloads, sha256, sig)
    self.add_daily_counts(s)


  def add_daily_counts(self, sample):
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
            sample.downloads, sample.sha256, sample.sig
            )
    if _VERBOSE:
      print('insert: %s %s %s %d' % (
          sample.sample_date, sample.product, sample.version, sample.downloads))
    if not self.dry_run:
      self.cursor.execute(cmd)


  def new_sample(self, sample, sample_day, downloads, sha256, sig):
    sample_date = (_EPOCH + datetime.timedelta(days=sample_day)
                   ).strftime('%Y-%m-%d')
    s = DownloadSample(
        file=sample.file,
        sample_date=sample_date,
        downloads_total=sample.downloads_total,
        sha256_total=sample.sha256_total,
        sig_total=sample.sig_total,
        product=sample.product,
        version=sample.version,
        arch=sample.arch,
        os=sample.os,
        extension=sample.extension,
        installer=sample.installer,
        downloads=downloads,
        sha256=sha256,
        sig=sig)
    self.history[(s.product, s.file, s.version, sample_day)] = s
    return s


def main():
  parser = argparse.ArgumentParser(
      description='Upload categorized download counts')

  parser.add_argument(
        '--database', default='metrics',
        help='Get all repositories rather than just the select ones')
  parser.add_argument(
        '--dry_run', '-n', action='store_true',
        help='Just print updates, do not commit them')
  parser.add_argument(
        '--backfill', type=bool, default=True,
        help='backfill gaps in data')
  parser.add_argument(
        '--window', type=int, default=14,
        help='How many days to look back in time')
  parser.add_argument('files', nargs='*')
  options = parser.parse_args()

  connection = cloudsql.Connect(options.database)
  history = gather_previous_downloads(connection, options.window)
  uploader = DailyCountUploader(
      history, connection, dry_run=options.dry_run, window=options.window,
      backfill=options.backfill)

  for file in options.files:
    uploader.upload_file(file)
  connection.close()


if __name__ == '__main__':
  main()
