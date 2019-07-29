# -*- coding: utf-8 -*-
"""Cursor support

"""
import cStringIO
import io
import math

import numpy
import pandas as pd
import pyarrow.parquet as pq
import json
from boto3.s3.transfer import TransferConfig, MB

from s3filter.sql.format import Format
from s3filter.util.constants import *
from s3filter.util.filesystem_util import *
from s3filter.util.timer import Timer
import http.client

class PandasCursor(object):
    """Represents a database cursor for managing the context of a fetch operation.

    Intended to be modelled after the Python DB API. All it supports at present is select, taking a s3 key and sql
    string to execute. The rows returned from s3 are returned as an iterator.

    Importantly supports streaming of records which gives more control over simply passing Python data structures
    around.

    """

    def __init__(self, s3):

        self.s3 = s3

        self.s3key = None
        self.s3sql = None
        self.event_stream = None
        self.table_local_file_path = None
        self.need_s3select = True

        self.timer = Timer()

        self.time_to_first_record_response = None
        self.time_to_last_record_response = None

        self.query_bytes = 0
        self.bytes_scanned = 0
        self.bytes_processed = 0
        self.bytes_returned = 0

        self.num_http_get_requests = 0
        self.table_data = None

        self.input = Format.CSV

    def parquet(self):
        self.input = Format.PARQUET
        return self

    def csv(self):
        self.input = Format.CSV
        return self

    def select(self, s3key, s3sql):
        """Creates a select cursor

        :param s3sql:  the sql to execute
        :param s3key: the s3 key to select against
        :return: the cursor
        """

        self.s3key = s3key
        self.s3sql = s3sql

        # TODO:only simple SQL queries are considered. Nested and complex queries will need a lot of work to handle
        self.need_s3select = not (s3sql.lower().replace(';', '').strip() == 'select * from s3object')

        # There doesn't seem to be a way to capture the bytes sent to s3, but we can use this for comparison purposes
        self.query_bytes = len(self.s3key.encode('utf-8')) + len(self.s3sql.encode('utf-8'))

        return self

    def execute(self):
        """Executes the fetch operation. This is different to the DB API as it returns an iterable. Of course we could
        model that API more precisely in future.

        :return: An iterable of the records fetched
        """
	
	"""
	All operations return a CSV file
	"""
	print("Executing Pandas cursor!")
	self.timer.start()
	self.input = Format.CSV
	
	config = TransferConfig(
                multipart_chunksize=8 * MB,
                multipart_threshold=8 * MB
	)
			
	
	try:	
		#h1 = http.client.HTTPConnection('127.0.0.1:5000')
		#h1 = http.client.HTTPConnection("3.87.65.94:5000")
		h1 = http.client.HTTPConnection(FILTER_IP)
		print("Connected")
		
        body_ = None

        if self.input is Format.CSV:
            body_ = json.dumps({"query":self.s3sql, "input":"CSV"})
        elif self.input is Format.PARQUET:
            body_ = json.dumps({"query":self.s3sql, "input":"PARQUET"})
        else:
            raise Exception("Unrecognised InputType {}".format(self.input))



		h1.request('POST','/' + S3_BUCKET_NAME + '/' + self.s3key, body=body_)
		print("Made request!")
		r = h1.getresponse()
		#print(r.read())
		r2 = r.read()#.decode("utf-8")
		#print(r2)	
		#LOST TO DO!!
		self.table_data = io.BytesIO()
		self.table_data.write(r2)
		
		print("HELLO!")
		print(self.table_data.getvalue().decode('utf-8'))
		self.num_http_get_requests = PandasCursor.calculate_num_http_requests(self.table_data, config)		
	
		return self.parse_file()	
	except Exception as e:
		print(e)
        
	#return self.parse_file()

    def parse_event_stream(self):
        """Generator that hands out records from the event stream lazily

        :return: Generator of the records returned from s3
        """

        prev_record_str = None

        records_str_rdr = cStringIO.StringIO()
        for event in self.event_stream:

            if 'Records' in event:

                elapsed_time = self.timer.elapsed()
                if self.time_to_first_record_response is None:
                    self.time_to_first_record_response = elapsed_time

                self.time_to_last_record_response = elapsed_time

                # records_str = event['Records']['Payload'].decode('utf-8')
                records_str = event['Records']['Payload']

                if prev_record_str is not None:
                    records_str_rdr.write(prev_record_str)
                    prev_record_str = None

                if records_str.endswith('\n') and not records_str.endswith('\\n'):
                    records_str_rdr.write(records_str)
                else:
                    last_newline_pos = records_str.rfind('\n', 0, len(records_str))
                    if last_newline_pos == -1:
                        prev_record_str = records_str
                    else:
                        prev_record_str = records_str[last_newline_pos + 1:]
                        records_str_rdr.write(records_str[:last_newline_pos + 1])

                if records_str_rdr.tell() > 1024 * 1024 * 16:
                    records_str_rdr.seek(0)
                    df = pd.read_csv(records_str_rdr, header=None, prefix='_', dtype=numpy.str, engine='c',
                                     quotechar='"', na_filter=False, compression=None, low_memory=False)
                    records_str_rdr.close()
                    records_str_rdr = cStringIO.StringIO()
                    yield df

                # Strangely the reading with the python csv reader and then loading into a dataframe "seems" faster than
                # reading csvs with pandas, agate is another option. need to test properly

                # record_rdr = agate.csv_py2.reader(records_str_rdr)
                # df = pd.DataFrame(list(record_rdr), dtype=str)
                # df = df.add_prefix('_')

                # record_rdr = csv.reader(records_str_rdr)
                # df = pd.DataFrame(list(record_rdr), dtype=str)
                # df = df.add_prefix('_')

            elif 'Stats' in event:
                self.bytes_scanned += event['Stats']['Details']['BytesScanned']
                self.bytes_processed += event['Stats']['Details']['BytesProcessed']
                self.bytes_returned += event['Stats']['Details']['BytesReturned']
                # print("{} Stats Event: bytes scanned: {}, bytes processed: {}, bytes returned: {}"
                #       .format(timeit.default_timer(), self.bytes_scanned, self.bytes_processed, self.bytes_returned))

            elif 'Progress' in event:
                pass
                # print("{} Progress Event".format(timeit.default_timer()))

            elif 'End' in event:
                # print("{} End Event".format(timeit.default_timer()))

                if records_str_rdr.tell() > 0:
                    records_str_rdr.seek(0)
                    df = pd.read_csv(records_str_rdr, header=None, prefix='_', dtype=numpy.str, engine='c',
                                     quotechar='"', na_filter=False, compression=None, low_memory=False)
                    records_str_rdr.flush()
                    records_str_rdr.close()
                    yield df

                return

            elif 'Cont' in event:
                pass
                # print("{} Cont Event".format(timeit.default_timer()))

            elif 'RequestLevelError' in event:
                raise Exception(event)
                # print("{} Cont Event".format(timeit.default_timer()))

            else:
                raise Exception("Unrecognized event {}".format(event))

    def parse_file(self):
        #try:
            if self.input is Format.CSV:
                if self.table_data and len(self.table_data.getvalue()) > 0:
                    ip_stream = cStringIO.StringIO(self.table_data.getvalue().decode('utf-8'))
                elif os.path.exists(self.table_local_file_path):
                    ip_stream = self.table_local_file_path
                else:
                    return

                self.time_to_first_record_response = self.time_to_last_record_response = self.timer.elapsed()
		print("Printing ipstream:")
		print(ip_stream.getvalue())
                for df in pd.read_csv(ip_stream, delimiter='|',
                                      header=None,
                                      prefix='_', dtype=numpy.str,
                                      engine='c', quotechar='"', na_filter=False, compression=None, low_memory=False,
                                      skiprows=1,
                                      chunksize=10 ** 7):
                    # Get read bytes
                    self.bytes_returned += ip_stream.tell()

                    # drop last column since the line separator | creates a new empty column at the end of every record
                    df_col_names = list(df)
                    last_col = df_col_names[-1]
                    df.drop(last_col, axis=1, inplace=True)

                    yield df
            elif self.input is Format.PARQUET:

                table = pq.read_table(self.table_data)
                self.table_data = None

                yield table.to_pandas()
            else:
                raise Exception("Unrecognized input type '{}'".format(self.input))
	
        #except Exception as e:
        #    print("can not read table data at with error {}".format(e.message))
        #    raise e
	
    def close(self):
        """Closes the s3 event stream

        :return: None
        """
        if self.event_stream:
            self.event_stream.close()
        if self.table_data:
            self.table_data.close()

    def save_table(self):
        """
        Saves the table data to disk
        :return:
        """
        if self.table_data:
            proj_dir = os.environ['PYTHONPATH'].split(":")[0]
            table_loc = os.path.join(proj_dir, TABLE_STORAGE_LOC)
            create_dirs(table_loc)

            self.table_local_file_path = os.path.join(table_loc, self.s3key)

            if not os.path.exists(self.table_local_file_path):
                create_file_dirs(self.table_local_file_path)
                with open(self.table_local_file_path, 'w') as table_file:
                    table_file.write(self.table_data.getvalue())

    @staticmethod
    def calculate_num_http_requests(table_data, config):
        if table_data is not None and len(table_data.getvalue()):
            shard_max_size = config.multipart_threshold
            return math.ceil(len(table_data.getvalue()) / (1.0 * shard_max_size))

        return 1
