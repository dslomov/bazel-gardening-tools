#!/usr/bin/env python3
"""Convert cumulative updates to daily.

Should eventually be combined with categorize tool.
"""


import argparse
import collections
import sys

import cloudsql


DownloadSample = collections.namedtuple(
    'DownloadSample',
    'file ymd hhmm downloads downloads_sha downloads_sig'
    ' product version arch os extension installer')


def ComputeDailyDownloads(connection, trailing_days):
  updates = []
  with connection.cursor() as cursor:
    cursor.execute(
        """
        select filename, version, sample_date,
               datediff(sample_date, '2019-01-01') as day,
               downloads, downloads_total,
               sha256, sha256_total,
               sig, sig_total
        from gh_downloads
        where sample_date >= date_sub(curdate(), interval %d day)
        order by filename, version, day
        """ % (trailing_days))

    last_day = None
    last_filename = None
    # really totals.
    last_downloads = last_sha256 = last_sig = 0
    while True:
      try:
        row = cursor.fetchone()
        if not row:
          break
      except Exception as e:
        print(e)
        continue

      if row:
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

        if (last_day and last_filename == filename
            and last_version == version):
          u_downloads = u_sha256 = u_sig = -1
          if downloads is None or downloads <= 0:
            u_downloads = downloads_total - last_downloads

          # This corrects the 2019-04-15 problem. We had no data between 4/2
          # and 4/15, so all the counts were too high. There were a few
          # gaps like this. For now, we just replace the one day with the
          # average. In the future, we could create dummy evetns to smooth
          # it out.
          n_days = day - last_day
          if n_days > 1:
            u_downloads = round((downloads_total - last_downloads) / n_days)
            if u_downloads != downloads:
              print("normalizing initial gap download: %s, %s %d -> %d" % (
                  sample_date, filename, downloads, u_downloads))
            else:
              u_downloads = -1

          if sha256 is None or sha256 <= 0:
            u_sha256 = sha256_total - last_sha256
          if sig is None or sig <= 0:
            u_sig = sig_total - last_sig
          if u_downloads > 0 or u_sha256 > 0 or u_sig > 0:
            updates.append((filename, version, sample_date, u_downloads, u_sha256, u_sig))

        last_filename = filename
        last_version = version
        last_day = day
        last_downloads = downloads_total
        last_sha256 = sha256_total
        last_sig = sig_total

  return updates


def ApplyUpdates(connection, updates, dry_run=True):
  upd_count = 0
  cursor = None
  for u in updates:
    if not dry_run and not cursor:
      cursor = connection.cursor()
    s = []
    if u[3] >= 0:
      s.append('downloads=%d' % u[3])
    if u[4] >= 0:
      s.append('sha256=%d' % u[4])
    if u[5] >= 0:
      s.append('sig=%d' % u[5])
    cmd = 'update gh_downloads set %s' % ','.join(s)
    cmd += ' where filename="%s" and version="%s" and sample_date="%s"' % (
        u[0], u[1], u[2])
    print(cmd)
    if not dry_run:
      cursor.execute(cmd)
    upd_count += 1
    if upd_count % 100 == 0:
      print('committing %d' % upd_count)
      if not dry_run:
        connection.commit()
        cursor = None
  if not dry_run and cursor:
    connection.commit()
  connection.close()
  print('updated %d records' % upd_count)


def main():
  parser = argparse.ArgumentParser(description='Compute Daily Downloads')

  parser.add_argument(
        '--database', default='metrics',
        help='Get all repositories rather than just the select ones')
  parser.add_argument(
        '--dry_run', '-n', action='store_true',
        help='Just print updates, do not commit them')
  parser.add_argument(
        '--window', type=int, default=7,
        help='How many days to look back in time')

  args = parser.parse_args()
  connection = cloudsql.Connect(args.database)
  updates = ComputeDailyDownloads(connection, 20)
  ApplyUpdates(connection, updates, args.dry_run)


if __name__ == '__main__':
  main()
