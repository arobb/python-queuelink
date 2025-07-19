"""Store and retrieve results from throughput tests"""
import os
import sqlite3
import sys

from datetime import datetime
from typing import Union

DB_NAME = 'throughput/throughput.sqlite.db'

CURRENT_SESSION_TABLE_NAME = 'current_session'
CURRENT_SESSION_TABLE_SCHEMA = 'parent_process_id, session_id, session_time, ' \
                               'UNIQUE(parent_process_id)'

TEST_SESSION_TABLE_NAME = 'sessions'
TEST_SESSION_TABLE_SCHEMA = 'session_id, time, UNIQUE(session_id)'

RESULT_TABLE_NAME = 'results'
RESULT_TABLE_SCHEMA = 'session_id, python_version, test_name, start_method, source, destination, ' \
                      'result, result_unit'


class ThroughputResults(object):
    """Manage results storage for QueueLink throughput tests."""
    def __init__(self,
                 session_id: str,
                 session_time: datetime,
                 start_method: str,
                 source_path: str,
                 dest_path: str):
        self.session_id = session_id
        self.session_time = session_time
        self.start_method = start_method
        self.source_path = source_path
        self.dest_path = dest_path
        self.db = sqlite3.connect(DB_NAME)

        # Create tables if needed
        cursor = self.db.cursor()
        for tbl, schema in [(TEST_SESSION_TABLE_NAME, TEST_SESSION_TABLE_SCHEMA),
                            (RESULT_TABLE_NAME, RESULT_TABLE_SCHEMA),
                            (CURRENT_SESSION_TABLE_NAME, CURRENT_SESSION_TABLE_SCHEMA)]:
            result = cursor.execute('SELECT name FROM sqlite_master WHERE name=?', (tbl,))
            if result.fetchone() is None:
                cursor.execute('CREATE TABLE IF NOT EXISTS ?(?)', (tbl, schema))

        # Session entry
        self.update_session_id()
        self.start_session()

    def update_session_id(self):
        """Uses parent PID to determine if we should use a different session ID and start time"""
        ppid = os.getppid()
        cursor = self.db.cursor()
        result = cursor.execute('SELECT parent_process_id, session_id, session_time FROM '
                                f'{CURRENT_SESSION_TABLE_NAME} '  # nosec
                                'WHERE parent_process_id = ?',
                                (ppid,))
        result_tuple = result.fetchone()

        if result_tuple is None:
            # None found, empty the table
            cursor.execute('DELETE FROM '
                           f'{CURRENT_SESSION_TABLE_NAME}')  # nosec

            time = self.session_time.strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute('INSERT INTO '
                           f'{CURRENT_SESSION_TABLE_NAME} '  # nosec
                           'VALUES ?, ?, ?',
                           (ppid, self.session_id, time))
            self.db.commit()

        else:
            session_id = result_tuple[1]
            session_time = result_tuple[2]

            self.session_id = session_id
            self.session_time = datetime.strptime(session_time, '%Y-%m-%d %H:%M:%S')

    def start_session(self):
        """Establish start time and write session information to DB."""
        time = self.session_time.strftime('%Y-%m-%d %H:%M:%S')
        cursor = self.db.cursor()
        cursor.execute('INSERT OR IGNORE INTO '
                       f'{TEST_SESSION_TABLE_NAME} '  # nosec
                       'VALUES (?, ?)',
                       (self.session_id, time))
        self.db.commit()

    def put(self, test_name: str,
            result: Union[int, float],
            result_unit: str):
        """Store a test result"""
        python_version = f'{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}'
        cursor = self.db.cursor()
        cursor.execute('INSERT INTO '
                       f'{RESULT_TABLE_NAME} '  # nosec
                       'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                       (self.session_id, python_version, test_name, self.start_method,
                        self.source_path, self.dest_path, result, result_unit))
        self.db.commit()


class ThroughputResultsOutput():
    """Format throughput results."""
    def __init__(self):
        self.db = sqlite3.connect(DB_NAME)
        self.db.row_factory = sqlite3.Row  # Set the kind of result objects that get returned

    def get_latest_session_id(self):
        """Get the session ID of the latest throughput session"""
        cursor = self.db.cursor()
        sql = ('SELECT session_id FROM '
               f'{TEST_SESSION_TABLE_NAME} '  # nosec
               'ORDER BY time DESC LIMIT 1')
        results = cursor.execute(sql).fetchone()

        return results['session_id'] if len(results) > 0 else None

    def get_session_results(self, session_id: str=None):
        """Get results of the specified (or latest) session"""
        if session_id is None:
            session_id = self.get_latest_session_id()

        # Records
        sql = ('SELECT python_version, test_name, start_method, source, destination, '
               '  CAST(ROUND(AVG(result), 6) AS TEXT) as result_avg, result_unit '
               f'FROM {RESULT_TABLE_NAME} '  # nosec
               'WHERE session_id = ? '
               'GROUP BY python_version, test_name, start_method, source, destination, '
               '  result_unit '
               'ORDER BY python_version DESC, test_name ASC, start_method ASC, source ASC, '
               '  destination ASC')
        cursor = self.db.cursor()
        results = cursor.execute(sql, (session_id,)).fetchall()

        # Add the column names as the first row
        if len(results) > 0:
            results.insert(0, results[0].keys())

        return results


if __name__ == "__main__":
    # Print the latest set of results
    results_object = ThroughputResultsOutput()
    results_list = results_object.get_session_results()

    print(f'Total rows: {len(results_list)-1}')

    # Column widths
    # https://sqlpey.com/python/top-5-methods-to-create-nicely-formatted-column-outputs-in-python/
    widths = [max(map(len, col))+2 for col in zip(*results_list)]

    # Print rows
    for i, row in enumerate(results_list):
        # if i > 20:
        #     break
        print(" ".join(val.ljust(width) for val, width in zip(row, widths)))
