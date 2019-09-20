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

_VERBOSE = False

# Report changes if they are over a given size and jumped by the given
# percentage
_MIN_DOWNLOADS_FOR_REPORTING = 10
_PERCENTAGE_CHANGE_TO_REPORT = 1.15

def none_to_null(s):
  if s == 'None':
    return ''
  return s


def str_to_date(s):
  return datetime.datetime.strptime(s, '%Y-%m-%d').date()

def date_to_str(dt):
  return dt.strftime('%Y-%m-%d')


def gather_previous_downloads(connection, trailing_days):
  """Get trailing_days worth of download records.

  Args:
    trailing_days: Number of days to look back in histroy.
  Returns:
    map: (product, filename, version, day) -> DownloadSample
  """
  ret = {}
  max_day = str_to_date('2019-01-01')
  with connection.cursor() as cursor:
    cursor.execute(
        """
        select product, filename, version, sample_date,
               downloads, downloads_total,
               sha256, sha256_total,
               sig, sig_total
        from gh_downloads
        where sample_date >= date_sub(curdate(), interval %d day)
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
        downloads = row['downloads']
        downloads_total = row['downloads_total']
        sha256 = row['sha256']
        sha256_total = row['sha256_total']
        sig = row['sig']
        sig_total = row['sig_total']
        ret[(product, filename, version, sample_date)] = DownloadSample(
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
        max_day = sample_date if sample_date > max_day else max_day
  print('Maximum day is', date_to_str(max_day))
  return ret


class DailyCountUploader(object):

  def __init__(self, history, connection, window=1, backfill=True,
               dry_run=True):
    # map: (product, filename, version, date) -> DownloadSample
    # Note that date is datetime.date, not a string of the date.
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
            sample_date=str_to_date(parts[1]),
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
    """Handle a download record.

    - compute download delta from previous (or earlier) day
    - (maybe) smooth sample over all days since last sample

    Args:
      sample: DownloadSample
    """

    downloads = sha256 = sig = 0

    if self.history.get(
        (sample.product, sample.file, sample.version, sample.sample_date)):
      raise Exception('We have already loaded %s %s %s %s' % (
          sample.product, sample.file, sample.version, sample.sample_date))

    previous = None
    days_to_previous = 0
    while not previous and days_to_previous <= self.window:
      days_to_previous += 1
      previous_date = sample.sample_date - datetime.timedelta(days=days_to_previous)
      previous = self.history.get(
          (sample.product, sample.file, sample.version, previous_date))

    if not previous:
      print(sample.product, sample.file, sample.version, sample.sample_date,
            '=No history')
    else:
      downloads = sample.downloads_total - previous.downloads_total
      sha256 = sample.sha256_total - previous.sha256_total
      sig = sample.sig_total - previous.sig_total

      # days_to_fill includes today.
      days_to_fill = (sample.sample_date - previous_date).days
      if days_to_fill != days_to_previous:
        print("GOT WRONG CALC for days_to_fill %d %d" % (
            days_to_fill, days_to_previous))
        return

      if self.backfill and days_to_fill > 1:
        # backfill algorithm:
        # - spread delta over all the days to be inserted. this includes
        #   the sample for today
        # - leave any rounding error in the sample for today.
        inc_downloads = downloads // days_to_fill
        inc_sha256 = sha256 // days_to_fill
        inc_sig = sig // days_to_fill

        for fill_index in range(1, days_to_fill):
          dt = previous_date + datetime.timedelta(days=fill_index)
          filler = self.new_sample(sample, inc_downloads, inc_sha256, inc_sig,
                                   sample_date=dt)
          # TODO(aiuto): Guard this with _VERBOSE after more flight time.
          print('backfill: %s %s %s: delta=%d, fill/day=%s' % (
              filler.sample_date, filler.product, filler.version,
              downloads, filler.downloads))
          self.add_daily_counts(filler)
          downloads -= inc_downloads
          sha256 -= inc_sha256
          sig -= inc_sig

      # assert: no need to backfill: downloads is what we got today
      # assert: with backfill: downloads holds ~avg/day change over period
      # assert: skip backfill: downloads holds multi-day delta
      if (downloads > _MIN_DOWNLOADS_FOR_REPORTING
          and int(previous.downloads * _PERCENTAGE_CHANGE_TO_REPORT) < downloads):
        print(sample.product, sample.file, sample.version,
              sample.sample_date, downloads,
              'large jump from %d' % previous.downloads)

    s = self.new_sample(sample, downloads, sha256, sig)
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


  def new_sample(self, sample, downloads, sha256, sig, sample_date=None):
    if not sample_date:
      sample_date = sample.sample_date
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
    self.history[(s.product, s.file, s.version, sample_date)] = s
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
