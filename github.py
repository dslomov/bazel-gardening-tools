"""Methods for talking to the github API."""

import datetime
import json
import urllib.request
import ssl

import database
import reports

ssl._create_default_https_context = ssl._create_unverified_context
secrets = json.load(open("secrets.json"))
client_id = secrets["client_id"]
client_secret = secrets["client_secret"]


GITHUB_API_URL_BASE = 'https://api.github.com/repos/'

_DEBUG = False

def add_client_secret(url):
    sep = '&'
    if not '?' in url:
        sep = '?'
    return url + sep + 'client_id=' + client_id + '&client_secret=' + client_secret


def get_next_url(response):
    if "Link" not in response:
        return None
    link_header = response["Link"]
    links = link_header.split(",")
    for link_segment in links:
        if link_segment.find("rel=\"next\"") == -1:
            continue
        link = link_segment[link_segment.index('<') +
                            1:link_segment.index('>')]
        return link
    return None


def fetch_issues(repo, query, modified_after=None):
    """Fetches issues from a repo.

    Args:
      repo: (str) '<organization>/<repo>'
      query: (str) optional query
      modified_after: (float) only fetch issues modified after this (UTC) time.
    """
    query_args = [
        'state=all',  # needed to get closed issues
        'per_page=100',
    ]
    if query:
        query_args.append(query)
    if modified_after:
        utc_time_s = datetime.datetime.utcfromtimestamp(
            modified_after).strftime('%Y-%m-%dT%H:%M:%SZ')
        query_args.append('since=%s' % utc_time_s)
        print('Fetching issues changed since: %s' % utc_time_s)
    url = GITHUB_API_URL_BASE + repo + '/issues?' + '&'.join(query_args)
    result = dict()
    i = 0
    while url:
        if _DEBUG:
            print(url)
        response = urllib.request.urlopen(add_client_secret(url))
        issues = json.loads(response.read())
        for issue in issues:
            result[issue["number"]] = issue
        url = get_next_url(response.info())
    print(len(result))
    return list(result.values())


def _fetch_all_from_repo(repo, resource):
    ret = []
    url = GITHUB_API_URL_BASE + repo + '/' + resource
    while url:
        if _DEBUG:
            print(url)
        response = urllib.request.urlopen(add_client_secret(url))
        more_data = json.loads(response.read())
        ret += more_data
        url = get_next_url(response.info())
    return ret


def fetch_labels(repo):
    return _fetch_all_from_repo(repo, 'labels')


def fetch_releases(repo):
    return _fetch_all_from_repo(repo, 'releases')


def fetch_repos(org):
  url = 'https://api.github.com/orgs/' + org + '/repos'
  ret = []
  while url:
    if _DEBUG:
      print(url)
    response = urllib.request.urlopen(add_client_secret(url))
    more_repos = json.loads(response.read())
    for repo in more_repos:
      ret.append(repo['full_name'])
    url = get_next_url(response.info())
  return ret
