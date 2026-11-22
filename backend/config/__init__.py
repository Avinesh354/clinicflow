# Fallback if mysqlclient cannot be installed (e.g. no wheel for your Python):
#   pip uninstall mysqlclient; pip install pymysql
try:
    import MySQLdb  # noqa: F401
except ImportError:  # pragma: no cover
    import pymysql
    pymysql.version_info = (2, 2, 1, "final", 0)
    pymysql.install_as_MySQLdb()
