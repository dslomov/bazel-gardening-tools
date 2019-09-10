#!/usr/bin/env python3
"""Tests for upload.py."""

import datetime
import unittest

import upload

_VERBOSE = False


def str_to_dt(s):
  return datetime.datetime.strptime(s, '%Y-%m-%d')


def dt_to_str(dt):
  return dt.strftime('%Y-%m-%d')


class UploadTest(unittest.TestCase):

  def setUp(self):
    history = {}
    self.uploader = upload.DailyCountUploader(
        history, None, dry_run=True, window=7, backfill=True)
    self.samples_added = []

    def add_called(sample):
      # capture each sample we would insert to database
      self.samples_added.append(sample)

    self.uploader.add_daily_counts = add_called

  def prep_history(self, fake_history):
    for fake in fake_history:
      sample_date = fake[0]
      sample_dt = str_to_dt(sample_date)
      sample_day = (sample_dt - upload._EPOCH).days
      product = fake[1]
      version = fake[2]
      downloads = fake[3]
      sha256 = fake[4]
      sig = fake[5]
      file = '%s-%s' % (product, version)
      fake_download_sample = upload.DownloadSample(
          sample_date=sample_date,
          file=file,
          product=product,
          version=version,
          downloads_total=downloads,
          sha256_total=sha256,
          sig_total=sig)
      self.uploader.new_sample(
          fake_download_sample, sample_day, downloads, sha256, sig)
    if _VERBOSE:
      for k, v in self.uploader.history.items():
        print(k, v.downloads_total, v.sha256_total, v.sig_total)


  def test_nobackfill(self):
    product = 'foo'
    version = '1'
    self.prep_history([
        ('2019-09-03', product, version, 50, 30, 10),
    ])
    last_dt = str_to_dt('2019-09-03')

    file = '%s-%s' % (product, version)
    sample_date = '2019-09-04'

    delta_downloads = 70
    delta_sha256 = 60
    delta_sig = 20

    s = upload.DownloadSample(
        sample_date=sample_date,
        file=file,
        product=product,
        version=version,
        downloads_total=50 + delta_downloads,
        sha256_total=30 + delta_sha256,
        sig_total=10 + delta_sig)
    self.uploader.process_sample(s)

    self.assertEqual(1, len(self.samples_added))
    self.assertEqual(delta_downloads, self.samples_added[0].downloads)
    self.assertEqual(delta_sha256, self.samples_added[0].sha256)
    self.assertEqual(delta_sig, self.samples_added[0].sig)


  def test_backfill(self):
    product = 'foo'
    version = '1'
    self.prep_history([
        ('2019-09-03', product, version, 50, 30, 10),
    ])
    last_dt = str_to_dt('2019-09-03')

    file = '%s-%s' % (product, version)
    sample_date = '2019-09-08'  # backfill 4 days
    n_backfill = 4

    delta_downloads = 70
    delta_sha256 = 60
    delta_sig = 20

    s = upload.DownloadSample(
        sample_date=sample_date,
        file=file,
        product=product,
        version=version,
        downloads_total=50 + delta_downloads * (n_backfill + 1) + 1,
        sha256_total=30 + delta_sha256 * (n_backfill  + 1)+ 2,
        sig_total=10 + delta_sig * (n_backfill + 1) + 3)
    self.uploader.process_sample(s)

    if _VERBOSE:
      for s in self.samples_added:
        print(s)

    self.assertEqual(n_backfill+1, len(self.samples_added))
    for n in range(n_backfill):
      self.assertEqual(
          dt_to_str(last_dt + datetime.timedelta(days=n+1)),
          self.samples_added[n].sample_date)
      self.assertEqual(
          (s.downloads_total - 50) // (n_backfill + 1),
          self.samples_added[n].downloads)
      self.assertEqual(
          (s.sha256_total - 30) // (n_backfill + 1),
          self.samples_added[n].sha256)
      self.assertEqual(
          (s.sig_total - 10) // (n_backfill + 1),
          self.samples_added[n].sig)

    # Not alignment with the sample created above
    self.assertEqual(delta_downloads + 1,
                     self.samples_added[n_backfill].downloads)
    self.assertEqual(delta_sha256 + 2, self.samples_added[n_backfill].sha256)
    self.assertEqual(delta_sig + 3, self.samples_added[n_backfill].sig)


if __name__ == '__main__':
  unittest.main()
