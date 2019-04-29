#!/usr/bin/env python3
"""Quick and dirty HTML writer."""

import re
import sys

HTML_SCRIPT_CODE = 'garden.js'

LINK_RE = re.compile(r'https?://[a-zA-Z0-9./-]*')


class HTMLWriter(object):

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
    return HTMLWriter.SPACE * n

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
      return HTMLWriter.Div(self, css_class)


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
      with HTMLWriter.TableCell(
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
      return HTMLWriter.TableRow(self.parent, heading=heading)

  def table(self):
      return HTMLWriter.Table(self)
