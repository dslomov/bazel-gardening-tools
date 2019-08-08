/* Categorized download counts */
/* TODO: Add a daily count field, compute as delta from previous day.
 *       Need an ETL pipeline to do this. Preferably cron job.
 */
CREATE TABLE IF NOT EXISTS gh_downloads(
  sample_date DATE,
  filename VARCHAR(200),
  downloads INT DEFAULT 0,  # downloads today
  downloads_total INT, # cumulative downloads of all time
  sha256 INT DEFAULT 0,
  sha256_total INT,
  sig INT DEFAULT 0,
  sig_total INT,
  product VARCHAR(50),
  version VARCHAR(50),
  arch VARCHAR(20),
  os VARCHAR(20),
  extension VARCHAR(10),
  is_installer BOOL
)

/*
 * This shows the downloads per day with the 3 OSes each in their own column.
 * It is not useful for datastudio.
 */
create view gh_downloads_by_day_unified as
select sample_date, product, version, sum(linux+macos+windows) 'all', sum(linux) 'linux', sum(macos) 'macos', sum(windows) 'windows'
from (
  select sample_date, product, version, sum(downloads) 'linux', 0 'macos', 0 'windows'
  from gh_downloads where os = 'linux'
  group by sample_date, product, version, os
  union all
  select sample_date, product, version, 0 'linux', sum(downloads) 'macos', 0 'windows'
  from gh_downloads where os = 'macos'
  group by sample_date, product, version, os
  union all
  select sample_date, product, version, 0 'linux', 0 'macos', sum(downloads) 'windows'
  from gh_downloads where os = 'windows'
  group by sample_date, product, version, os
  ) clustered
group by sample_date, product, version;




/*
 * Queries for data studio are prefixed by ds_.
 *
 * Notes:
 * 1. They must present dates as "YYYYMMDD", not as a natural date. (Sigh.)
 *    In DataStudio, you then must change type back to date. (Are you joking?)
 * 2. When they include product, remember to add a filter by product=bazel
 */

/* cumulative github downloads */
create view ds_github_downloads_by_day_by_os as
select date_format(sample_date, "%Y%m%d") "sample_date", product, os, sum(downloads) "downloads"
from gh_downloads
group by sample_date, product, os;


create view ds_gh_downloads_by_version_by_day as
select date_format(sample_date, "%Y%m%d") "sample_date", product, version,
       os, sum(downloads) "downloads"
from gh_downloads
group by sample_date, product, version, os;
