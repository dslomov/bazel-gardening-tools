"""Methods for interfacing with a CloudSQL instance."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import getpass
import pymysql


def Connect(database):
  """Connects to a mysql SQL database.

  Args:
    database: database connection id.
  Returns:
    a mysql Connection object.
  """
  user=getpass.getuser()
  connection = pymysql.connect(
      host='localhost',
      user=user,
      password=getpass.getpass(
          prompt='password for %s@%s: ' % (user, database)),
      db=database,
      charset='utf8',
      cursorclass=pymysql.cursors.DictCursor)
  return connection
