# -*- coding: utf-8 -*-
"""Filter query tests

"""
import os

from s3filter import ROOT_DIR
from s3filter.op.collate import Collate
#from s3filter.op.filter import Filter
from s3filter.op.project import Project
from s3filter.op.predicate_expression import PredicateExpression
from s3filter.op.sql_table_scan import SQLTableScan
from s3filter.plan.query_plan import QueryPlan
from s3filter.sql.function import timestamp, cast
from s3filter.util.test_util import gen_test_id
import pandas as pd

from s3filter.sql.format import Format

def test_filter_baseline():
    """

    :return:
    """

    query_plan = QueryPlan(buffer_size=64 ,is_async=True , use_shared_mem=False)

    # Query plan
    '''
    ts = query_plan.add_operator(
        SQLTableScan('lineitem.csv', 'select * from S3Object limit 3;' , False, 'ts', query_plan, False))
    '''
# using a 'use_native=True' argument will result in a None object being returned
    ts = query_plan.add_operator(
        SQLTableScan('random_strings_2.csv', 'select * from S3Object limit 3;',Format.CSV , True, False,False, 'ts', query_plan, False))
    f = query_plan.add_operator(
        Filter(PredicateExpression(lambda t_: cast(t_['_10'], timestamp) >= cast('1996-03-01', timestamp)),
               'f', query_plan,
               False))

    c = query_plan.add_operator(Collate('c', query_plan, False))

    ts.connect(f)
    f.connect(c)

    # Write the plan graph
    query_plan.write_graph(os.path.join(ROOT_DIR, "../tests-output"), gen_test_id())

    # Start the query
    query_plan.execute()

    # Assert the results
    # num_rows = 0
    # for t in c.tuples():
    #     num_rows += 1
    #     print("{}:{}".format(num_rows, t))
    print(len(c.tuples()))
    assert 2 + 1 == len(c.tuples())

    field_names = ['_0', '_1', '_2', '_3', '_4', '_5', '_6', '_7', '_8', '_9', '_10', '_11', '_12', '_13', '_14', '_15']

    assert c.tuples()[0] == field_names

    assert c.tuples()[1] == ['1', '155190', '7706', '1', '17', '21168.23', '0.04', '0.02', 'N', 'O', '1996-03-13',
                             '1996-02-12', '1996-03-22', 'DELIVER IN PERSON', 'TRUCK', 'egular courts above the']

    assert c.tuples()[2] == ['1', '67310', '7311', '2', '36', '45983.16', '0.09', '0.06', 'N', 'O', '1996-04-12',
                             '1996-02-28', '1996-04-20', 'TAKE BACK RETURN', 'MAIL',
                             'ly final dependencies: slyly bold ']

    # Write the metrics
    query_plan.print_metrics()


def test_filter_empty():
    """Executes a filter where no records are returned. We tst this as it's somewhat peculiar with s3 select, in so much
    as s3 does not return column names when selecting data, meaning, unlike a traditional DBMS, no field names tuple
    should be present in the results.

    :return: None
    """

    query_plan = QueryPlan()

    # Query plan
    ts = query_plan.add_operator(
        SQLTableScan('lineitem.csv', 'select * from S3Object limit 0;', False, 'ts', query_plan, False))

    f = query_plan.add_operator(
        Filter(PredicateExpression(lambda t_: cast(t_['_10'], timestamp) >= cast('1996-03-01', timestamp)),
               'f', query_plan,
               False))

    c = query_plan.add_operator(Collate('c', query_plan, False))

    ts.connect(f)
    f.connect(c)

    # Write the plan graph
    query_plan.write_graph(os.path.join(ROOT_DIR, "../tests-output"), gen_test_id())

    # Start the query
    query_plan.execute()

    # Assert the results
    # num_rows = 0
    # for t in c.tuples():
    #     num_rows += 1
    #     print("{}:{}".format(num_rows, t))

    assert len(c.tuples()) == 0

    # Write the metrics
    query_plan.print_metrics()


def test_pandas_filter_baseline():
    """

    :return:
    """

    query_plan = QueryPlan(buffer_size=8192)

    # Query plan
    ts = query_plan.add_operator(
        SQLTableScan('lineitem.csv', 'select * from S3Object limit 3;', True, 'ts', query_plan, False))

    # f = query_plan.add_operator(
    #     Filter(PredicateExpression(lambda t_: cast(t_['_10'], timestamp) >= cast('1996-03-01', timestamp)),
    #            'f', query_plan,
    #            False))

    def pd_expr(df):
        # df['_10'] = pd.to_datetime(df['_10'])
        return pd.to_datetime(df['_10']) >= '1996-03-01'

    f = query_plan.add_operator(
        Filter(PredicateExpression(None, pd_expr),
               'f', query_plan,
               True))

    c = query_plan.add_operator(Collate('c', query_plan, False))

    ts.connect(f)
    f.connect(c)

    # Write the plan graph
    query_plan.write_graph(os.path.join(ROOT_DIR, "../tests-output"), gen_test_id())

    # Start the query
    query_plan.execute()

    # Assert the results
    # num_rows = 0
    # for t in c.tuples():
    #     num_rows += 1
    #     print("{}:{}".format(num_rows, t))

    assert 2 + 1 == len(c.tuples())

    field_names = ['_0', '_1', '_2', '_3', '_4', '_5', '_6', '_7', '_8', '_9', '_10', '_11', '_12', '_13', '_14',
                   '_15']

    assert c.tuples()[0] == field_names

    assert c.tuples()[1] == ['1', '155190', '7706', '1', '17', '21168.23', '0.04', '0.02', 'N', 'O', '1996-03-13',
                             '1996-02-12', '1996-03-22', 'DELIVER IN PERSON', 'TRUCK', 'egular courts above the']

    assert c.tuples()[2] == ['1', '67310', '7311', '2', '36', '45983.16', '0.09', '0.06', 'N', 'O', '1996-04-12',
                             '1996-02-28', '1996-04-20', 'TAKE BACK RETURN', 'MAIL',
                             'ly final dependencies: slyly bold ']

    # Write the metrics
    query_plan.print_metrics()



def test_filter_1():
    """

    :return:
    """

    query_plan = QueryPlan(buffer_size=64 ,is_async=True , use_shared_mem=False)

    # Query plan
    
    ts = query_plan.add_operator(
        SQLTableScan('tpch-sf1/lineitem_sharded/lineitem.csv.0', 'select * from S3Object where cast(l_extendedprice as float) >= 0 and cast(l_extendedprice  as float)<= 910;' ,Format.CSV , True, False,False, 'ts', query_plan, False))
    
# using a 'use_native=True' argument will result in a None object being returned
    '''
    ts = query_plan.add_operator(
        SQLTableScan('tpch-sf1/lineitem_sharded/lineitem.csv.0', 'select l_partkey  from S3Object limit 5;',Format.CSV , True, False,False, 'ts', query_plan, False))
    #random_strings_2.csv
    '''
    c = query_plan.add_operator(Collate('c', query_plan, False))
     
    ts.connect(c)
    #f.connect(c)
       
    # Write the plan graph
    query_plan.write_graph(os.path.join(ROOT_DIR, "../tests-output"), gen_test_id())

    # Start the query
    query_plan.execute()

    #assert 2 + 1 == len(c.tuples())
    print("Tuples:")
    print(c.tuples())
    # Write the metrics
    query_plan.print_metrics()
    print(ROOT_DIR)



def test_filter_arg(object_, sql_query):
    # Let's forget about the local filter for now. The pd._expr field of the PredicateExpression class is not well documented and it is needed for the Filter class (on line 102).
    """

    :return:
    """

    query_plan = QueryPlan(buffer_size=64 ,is_async=True , use_shared_mem=False)

    # Query plan
    '''
    ts = query_plan.add_operator(
        SQLTableScan('lineitem.csv', 'select * from S3Object limit 3;' , False, 'ts', query_plan, False))
    '''
# using a 'use_native=True' argument will result in a None object being returned
    ts = query_plan.add_operator(
        SQLTableScan(object_, sql_query, Format.CSV , True, False,False, 'ts', query_plan, False))
    
   


    c = query_plan.add_operator(Collate('c', query_plan, False))

    ts.connect(c)


    # Write the plan graph
    query_plan.write_graph(os.path.join(ROOT_DIR, "../tests-output"), gen_test_id())

    # Start the query
    query_plan.execute()

    #assert 2 + 1 == len(c.tuples())
    print("Tuples:")
    print(c.tuples())
    # Write the metrics
    query_plan.print_metrics()
    print(ROOT_DIR)

queries= [ "select * from S3Object where cast(l_extendedprice as float) >= {} and cast(l_extendedprice as float) <= {};".format(0, 910) ,'select * from S3Object ;']
for q in queries:
    for i in range(10):
        test_filter_arg('lineitem_725M.tbl', q)


'''
test_filter_arg('test_table.csv')

test_filter_arg('partsupp.tbl')

test_filter_arg('lineitem.tbl')

test_filter_arg('big_file.tbl')
'''