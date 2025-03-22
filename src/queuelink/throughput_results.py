"""Store and retrieve results from throughput tests"""
import os
import sqlite3
import sys

from datetime import datetime
from typing import Union

db_name = 'throughput/throughput.sqlite.db'

current_session_table_name = 'current_session'
current_session_table_schema = 'parent_process_id, session_id, session_time, ' \
                               'UNIQUE(parent_process_id)'

test_session_table_name = 'sessions'
test_session_table_schema = 'session_id, time, UNIQUE(session_id)'

result_table_name = 'results'
result_table_schema = 'session_id, python_version, test_name, start_method, source, destination, ' \
                      'result, result_unit'


class ThroughputResults(object):
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
        self.db = sqlite3.connect(db_name)

        # Create tables if needed
        cursor = self.db.cursor()
        for tbl, schema in [(test_session_table_name, test_session_table_schema),
                            (result_table_name, result_table_schema),
                            (current_session_table_name, current_session_table_schema)]:
            result = cursor.execute(f'SELECT name FROM sqlite_master WHERE name="{tbl}"')
            if result.fetchone() is None:
                cursor.execute(f'CREATE TABLE IF NOT EXISTS {tbl}({schema})')

        # Session entry
        self.update_session_id()
        self.start_session()

    def update_session_id(self):
        """Uses parent PID to determine if we should use a different session ID and start time"""
        ppid = os.getppid()
        sql = f'SELECT parent_process_id, session_id, session_time FROM ' \
              f'{current_session_table_name} WHERE parent_process_id = "{ppid}"'

        cursor = self.db.cursor()
        result = cursor.execute(sql)
        result_tuple = result.fetchone()
        if result_tuple is None:
            # None found, empty the table
            sql = f'DELETE FROM {current_session_table_name}'
            cursor.execute(sql)

            time = self.session_time.strftime('%Y-%m-%d %H:%M:%S')
            sql = f'INSERT INTO {current_session_table_name} VALUES ' \
                  f'("{ppid}", "{self.session_id}", "{time}")'
            cursor.execute(sql)
            self.db.commit()

        else:
            session_id = result_tuple[1]
            session_time = result_tuple[2]

            self.session_id = session_id
            self.session_time = datetime.strptime(session_time, '%Y-%m-%d %H:%M:%S')

    def start_session(self):
        time = self.session_time.strftime('%Y-%m-%d %H:%M:%S')
        sql = f'INSERT OR IGNORE INTO {test_session_table_name} VALUES ("{self.session_id}", ' \
              f'"{time}")'

        cursor = self.db.cursor()
        cursor.execute(sql)
        self.db.commit()

    def put(self, test_name: str,
            result: Union[int, float],
            result_unit: str):
        """Store a test result"""
        python_version = f'{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}'

        sql = f"""INSERT INTO {result_table_name} VALUES
            ('{self.session_id}', '{python_version}', '{test_name}', '{self.start_method}', 
            '{self.source_path}', '{self.dest_path}', '{result}', '{result_unit}')
        """

        cursor = self.db.cursor()
        cursor.execute(sql)
        self.db.commit()


class ThroughputResultsOutput():
    def __init__(self):
        self.db = sqlite3.connect(db_name)
        self.db.row_factory = sqlite3.Row  # Set the kind of result objects that get returned

    def get_latest_session_id(self):
        """Get the session ID of the latest throughput session"""
        sql = f'SELECT session_id FROM {test_session_table_name} ORDER BY time DESC LIMIT 1'
        cursor = self.db.cursor()
        results = cursor.execute(sql).fetchone()

        return results['session_id'] if len(results) > 0 else None

    def get_session_results(self, session_id: str=None):
        """Get results of the specified (or latest) session"""
        if session_id is None:
            session_id = self.get_latest_session_id()

        # Columns
        columns = ['python_version', 'test_name', 'start_method', 'source', 'destination',
                   'CAST(ROUND(AVG(result), 6) AS TEXT) as result_avg', 'result_unit']

        # Records
        sql = (f'SELECT {",".join(columns)} '
               f'FROM {result_table_name} '
               f'WHERE session_id = "{session_id}" '
               f'GROUP BY python_version, test_name, start_method, source, destination, '
               f'  result_unit '
               f'ORDER BY python_version DESC, test_name ASC, start_method ASC, source ASC, '
               f'  destination ASC')
        cursor = self.db.cursor()
        results = cursor.execute(sql).fetchall()

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
