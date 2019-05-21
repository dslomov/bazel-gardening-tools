CREATE TABLE IF NOT EXISTS gh_downloads(
  sample_date DATE,
  filename VARCHAR(200),
  downloads INT, # counts are cummulative
  sha256 INT,
  sig INT,
  product VARCHAR(50),
  version VARCHAR(50),
  arch VARCHAR(20),
  os VARCHAR(20),
  extension VARCHAR(10),
  is_inst BOOL
)

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
group by sample_date, product, version


create view gh_downloads_by_day_by_os as
select sample_date, product, version, os, sum(downloads) 'downloads'
from gh_downloads
group by sample_date, product, version, os;
