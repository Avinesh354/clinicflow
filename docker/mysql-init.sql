-- Django's test runner creates/drops a test_* database; the app user needs rights on it.
GRANT ALL PRIVILEGES ON `test\_%`.* TO 'clinicflow'@'%';
