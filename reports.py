#!/usr/bin/env python3

import collections
import datetime
import itertools
import os
import re
import sys

import database

HTML_SCRIPT_CODE = 'garden.js'

LINK_RE = re.compile(r'https?://[a-zA-Z0-9./-]*')

CAT_2_TEAM = {
    'category: BEP': 'team-Remote-Exec',
    'category: correctness / reproducibility': 'team-Configurability',
    'category: extensibility > toolchains': 'team-Configurability',
    'category: local execution / caching': 'team-Local-Exec',
    'category: misc > misc': 'team-Product',
    'category: misc > release / binary': 'team-Product',
    'category: misc > testing': 'team-Performance',
    'category: rules > java': 'team-Rules-Java',
    'category: rules > misc native': 'team-Rules-Server',
    'category: rules > ObjC / iOS / J2ObjC': 'team-Apple',
    'category: sandboxing': 'team-Local-Exec',
    'category: skylark > pkg build defs': 'team-Rules-Server',
}

#
# Helpers
#


# GitHub API datetime-stamps are already in UTC / Zulu time (+0000)
def parse_datetime(datetime_string):
    return datetime.datetime.strptime(datetime_string, "%Y-%m-%dT%H:%M:%SZ")


def issue_url(issue):
    return issue["html_url"]


def team_labels(labels):
    for l in labels:
        if l["name"].startswith("team-"):
            yield l


def category_labels(labels):
    for l in labels:
        name = l["name"]
        if name.startswith("category:"):
            yield name


def all_teams(labels):
    for team_label in team_labels(labels):
        yield team_label["name"]


#
# Issue predicates
#


def is_open(issue):
    return issue["state"] == "open"


def has_team_label(issue):
    for _ in team_labels(issue["labels"]):
        return True
    return False


def is_pull_request(issue):
    return "pull_request" in issue


def has_label(issue, label):
    for l in issue["labels"]:
        if l["name"] == label:
            return True
    return False


def get_any_of_labels(issue, labels):
    for l in issue["labels"]:
        if l["name"] in labels:
            return l["name"]
    return None


def has_priority(issue):
    return get_any_of_labels(issue, ["P0", "P1", "P2", "P3", "P4"]) != None

def get_priority(issue):
    return get_any_of_labels(issue, ["P0", "P1", "P2", "P3", "P4"])

def needs_more_data(issue):
    return has_label(issue, "more data needed")


def work_in_progress(issue):
    return has_label(issue, "WIP")


def teams(issue):
    return map(lambda i: i["name"], team_labels(issue["labels"]))


def latest_update_days_ago(issue):
    return (datetime.datetime.now() - parse_datetime(issue["updated_at"])).days


def is_stale(issue, days_ago):
    return latest_update_days_ago(issue) >= days_ago


def has_cla(issue):
    return has_label(issue, "cla: yes")


#
# Reports
#


def print_report(issues, header, predicate, printer):
    print(header)
    count = 0
    for issue in issues:
        if predicate(issue):
            count = count + 1
            print(printer(issue))
    print("%d issues" % count)
    print("---------------------------")


def print_report_group_by_team(issues, header, predicate, printer):
    def teamof(issue):
        t = list(teams(issue))
        if len(t) == 0:
            return "<No team>"
        else:
            return t[0]

    print(header)
    sorted_issues = sorted(filter(predicate, issues), key=teamof)
    for team, issues in itertools.groupby(sorted_issues, teamof):
        print("%s:" % team)
        for issue in issues:
            print(printer(issue))
    print("---------------------------")


def make_console_printer(
        show_age=False,
        show_number=True,
        show_url=True,
        show_title=False,
        show_teams=False):
    """A customizable console printer."""

    def truncate(string, length):
        return string[:length] + ".." if len(string) > length else string

    def printer(issue):
        output = []

        if show_age:
            output.append(("{: <4}", latest_update_days_ago(issue)))
        if show_number:
            output.append(("{: <4}", issue["number"]))
        if show_url:
            output.append(("{: <47}", issue_url(issue)))
        if show_title:
            output.append(("{: <50}", truncate(issue["title"], 48)))
        if show_teams:
            output.append(("{: <30}", truncate(",".join(teams(issue)), 28)))

        return " | ".join([parts[0] for parts in output
                           ]).format(*[parts[1] for parts in output])

    return printer


def issues_without_team(reporter, issues):
    reporter(
        issues,
        header="Open issues not assigned to any team",
        predicate=lambda issue: is_open(issue) and not (
            has_team_label(issue) or has_label(issue, 'release')),
        printer=make_console_printer(show_title=True),
    )


def more_than_one_team(reporter, issues):
    def predicate(issue):
        return is_open(issue) and len(list(teams(issue))) > 1

    reporter(
        issues,
        header="Issues assigned to more than one team:",
        predicate=predicate,
        printer=make_console_printer(show_teams=True))


def have_team_no_untriaged_no_priority(reporter, issues):
    reporter(
        issues,
        header="Triaged issues without priority",
        predicate=lambda issue: is_open(issue)
                                and has_team_label(issue)
                                and not has_label(issue, "untriaged")
                                and not has_priority(issue)
                                and not needs_more_data(issue)
                                and not is_pull_request(issue),
        printer=make_console_printer(show_teams=True))


_REPORTS = {
    "more_than_one_team":
        lambda issues: more_than_one_team(print_report, issues),
    "issues_without_team":
        lambda issues: issues_without_team(print_report, issues),
    "triaged_no_priority":
        lambda issues: have_team_no_untriaged_no_priority(
            print_report_group_by_team, issues),
}


def report(which_reports):
    issues = database.get_issues()
    for r in which_reports:
        _REPORTS[r](issues)


def ReportNames():
    return _REPORTS.keys()


class HTMLPrinter(object):

  SPACE = '&nbsp;'

  def __init__(self, out=sys.stdout):
    self.out = out
    self.in_row = False

  def write(self, content):
    self.out.write(content)

  def nl(self):
    self.out.write('<br/>')

  def preamble(self, css):
    self.write('<!DOCTYPE html>\n<html lang="en">')
    self.write('<head>\n')
    self.write('<meta charset="utf-8">\n')
    if css:
      self.write('<style>\n')
      self.write(css)
      self.write('</style>\n')
    self.write('<script type="text/javascript" src="%s"></script>\n' % HTML_SCRIPT_CODE)

  def done(self):
    self.write('</html>\n')

  @staticmethod
  def B(content):
    return ''.join(['<b>', content, '</b>'])

  @staticmethod
  def space(n):
    return HTMLPrinter.SPACE * n

  @staticmethod
  def Link(content, link):
      return '<a href="%s" target=_none>%s</a>' % (link, content)

  class Div(object):
    def __init__(self, parent, css_class):
      self.parent = parent
      self.css_class = css_class

    def __enter__(self):
      self.parent.write('<div class="%s">' % self.css_class)
      return self

    def __exit__(self, unused_type, unused_value, unused_traceback):
      self.parent.write('</div>')

  def div(self, css_class):
      return HTMLPrinter.Div(self, css_class)


  class TableRow(object):

    def __init__(self, parent, heading=False):
      self.parent = parent
      self.heading = heading

    def write(self, content):
      self.parent.write(content)

    def __enter__(self):
      self.write('<tr>\n')
      return self

    def __exit__(self, unused_type, unused_value, unused_traceback):
      self.write('</tr>\n')

    def cell(self, content, rowspan=None, colspan=None, css_class=None,
             make_links=False):
      with HTMLPrinter.TableCell(
          self, rowspan=rowspan, colspan=colspan, css_class=css_class,
          make_links=make_links) as c:
        c.write(content)


  class TableCell(object):

    def __init__(self, parent, rowspan=None, colspan=None, css_class=None,
                 make_links=False):
      self.parent = parent
      self.rowspan = rowspan
      self.colspan = colspan
      self.css_class = css_class
      self.make_links = make_links

    def write(self, content, css_class=None):
      if self.make_links and content.find('<a href') < 0:
        pos = 0
        while True:
          m = LINK_RE.search(content, pos)
          if not m:
            break
          txt = m.group(0)
          if txt.startswith('https://github.com/bazelbuild'):
            txt = txt[29:]
          link = '<a href="%s" target=_none>%s</a>' % (m.group(0), txt)
          content = content[0:m.start()] + link + content[m.end():]
          pos = m.start() + len(link)

      if css_class:
        self.write('<div class="%s">' % self.css_class)
      one_line = len(content) < 70
      if not one_line:
        self.write('\n    ')
      self.parent.write(content.replace('\r', '').replace('\n', '<br/>'))
      if not one_line:
        self.write('\n  ')
      if css_class:
        self.write('</div>')

    def __enter__(self):
      tag = 'td' if not self.parent.heading else 'th'
      if self.rowspan:
        tag = tag + ' rowspan="%d"' % self.rowspan
      if self.colspan:
        tag = tag + ' colspan="%d"' % self.colspan
      # write through parent to avoid link expand
      self.parent.write('  <%s>' % tag)
      if self.css_class:
        self.write('<div class="%s">' % self.css_class)
      return self

    def __exit__(self, unused_type, unused_value, unused_traceback):
      if self.css_class:
        self.write('</div>')
      self.parent.write('</td>\n' if not self.parent.heading else '</th>\n')


  class Table(object):
    def __init__(self, parent):
      self.parent = parent

    def write(self, content):
      self.parent.write(content)

    def __enter__(self):
      self.write('<table>\n')
      return self

    def __exit__(self, unused_type, unused_value, unused_traceback):
      self.write('</table>\n')

    def row(self, heading=False):
      return HTMLPrinter.TableRow(self.parent, heading=heading)

  def table(self):
      return HTMLPrinter.Table(self)


def html_garden():
    issues = database.get_issues()
    c_groups = collections.defaultdict(list)
    predicate = lambda issue: is_open(issue) and not (
        has_team_label(issue) or has_label(issue, "release"))
    for issue in filter(predicate, issues):
        categories = category_labels(issue["labels"])
        if not categories:
            categories = ["uncategorized"]
        for c in categories:
            c_groups[c].append(issue)

    p = HTMLPrinter()
    p.preamble(
        """
        table, th, td {
            border: 1px solid black;
            border-collapse: collapse;
            vertical-align: top;
        }
        th, td {
            padding: 5px;
            text-align: left;
        }
        div.issue_text {
            max-width: 50em;
            padding: 5px;
            text-align: left;
            word-wrap: break-word;
        }
        """)
    for category in c_groups.keys():
        p.write(p.B('Category: %s (%d issues)' % (category, len(c_groups[category]))))
        with p.table() as table:
            with table.row(heading=True) as row:
                row.cell('Issue')
                row.cell('Age')
                row.cell('Description')
            for issue in sorted(
                c_groups[category],
                reverse=True,
                key=lambda issue: latest_update_days_ago(issue)):
                with table.row() as row:
                    row.cell(issue_url(issue), rowspan=2, make_links=True)
                    with HTMLPrinter.TableCell(row,
                                               css_class='issue_text') as c:
                        c.write(p.B(issue['title']))
                        c.write(p.space(5))
                        # TODO(aiuto): If they are a Googler, put a G logo next to them.
                        # This is availble through github.corp.google.com API.
                        user =  database.created_by(issue)
                        c.write(p.Link(user.name, user.link))
                    with HTMLPrinter.TableCell(row, rowspan=2) as c:
                        c.write(p.B('%d days old'
                                    % latest_update_days_ago(issue)))
                        p.nl();
                        p.nl();
                        priority = get_priority(issue)
                        if priority:
                          c.write(p.B('Priority: %s' % priority))
                          p.nl();

                        p.nl();
                        c.write(p.B('Assignees:'))
                        assignees = issue['assignees']
                        if len(assignees) > 0:
                          for user_data in assignees:
                            user = database.User(user_data)
                            p.nl();
                            c.write(p.space(5))
                            c.write(p.Link(user.name, user.link))
                        else: 
                          c.write(' [unassigned];')
                        p.nl();

                        c.write(p.B('Labels:'))
                        p.nl();
                        for label in issue['labels']:
                          name = label['name']
                          if not (name.startswith('P') and len(name) == 2):
                            c.write(p.space(5))
                            c.write(name)
                            p.nl();

                        for cat in category_labels(issue['labels']):
                          proposed_team = CAT_2_TEAM.get(cat)
                          if proposed_team:
                            p.nl();
                            c.write(
                                """<button onclick="replaceLabel('%s', '%s', '%s')">"""
                                """Move to %s"""
                                """</button>""" % (
                                    issue['url'], cat, proposed_team,
                                    proposed_team))

                with table.row() as row:
                    row.cell(issue['body'], css_class='issue_text',
                             make_links=True)
    p.done()


#
# Gardening
#

def issues_to_garden(reporter, issues, stale_for_days):
    def predicate(issue):
        return \
            not has_team_label(issue) \
            and not issue["assignee"] \
            and not is_pull_request(issue) \
            and is_stale(issue, stale_for_days) \
            and not work_in_progress(issue)

    reporter(
        issues,
        header="Open issues not assigned to any team or person",
        predicate=predicate,
        printer=make_console_printer(
            show_age=True, show_number=False, show_title=True))


def pull_requests_to_garden(reporter, issues, stale_for_days):
    def predicate(issue):
        return \
            not has_team_label(issue) \
            and not issue["assignee"] \
            and is_pull_request(issue) \
            and is_stale(issue, stale_for_days) \
            and not work_in_progress(issue) \
            and has_cla(issue)

    reporter(
        issues,
        header="Open pull requests not assigned to any team or person",
        predicate=predicate,
        printer=make_console_printer(
            show_age=True, show_number=False, show_title=True))


def garden(list_issues, list_pull_requests, stale_for_days):
    # We are only gardening open issues
    issues = database.get_issues(is_open)
    if list_issues:
        issues_to_garden(print_report, issues, stale_for_days)
    if list_pull_requests:
        pull_requests_to_garden(print_report, issues, stale_for_days)
