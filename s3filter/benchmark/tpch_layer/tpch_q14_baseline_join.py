# -*- coding: utf-8 -*-
"""TPCH Q14 Baseline Join Benchmark

"""

import os
from datetime import datetime, timedelta

import numpy
import numpy as np
import pandas as pd

import s3filter.util.constants
from s3filter import ROOT_DIR
from s3filter.benchmark.tpch import tpch_results
from s3filter.op.aggregate import Aggregate
from s3filter.op.aggregate_expression import AggregateExpression
from s3filter.op.hash_join_build import HashJoinBuild
from s3filter.op.hash_join_probe import HashJoinProbe
from s3filter.op.join_expression import JoinExpression
from s3filter.op.map import Map
from s3filter.op.operator_connector import connect_many_to_many, connect_all_to_all, connect_many_to_one, \
    connect_one_to_one
from s3filter.plan.query_plan import QueryPlan
from s3filter.query import tpch_q14
from s3filter.sql.format import Format
from s3filter.util.test_util import gen_test_id


def main(sf, lineitem_parts, lineitem_sharded, part_parts, part_sharded, other_parts, expected_result, format_):
    run(parallel=True, use_pandas=True, secure=False, use_native=False, buffer_size=0, lineitem_parts=lineitem_parts,
        part_parts=part_parts, lineitem_sharded=lineitem_sharded, part_sharded=part_sharded, other_parts=other_parts,
        sf=sf,
        expected_result=expected_result, format_=format_)


def run(parallel, use_pandas, secure, use_native, buffer_size, lineitem_parts, part_parts, lineitem_sharded,
        part_sharded, other_parts, sf, expected_result, format_):
    """

    :return: None
    """

    print('')
    print("TPCH Q14 Baseline Join")
    print("----------------------")

    query_plan = QueryPlan(is_async=parallel, buffer_size=buffer_size)

    # Query plan
    # DATE is the first day of a month randomly selected from a random year within [1993 .. 1997].
    date = '1993-01-01'
    min_shipped_date = datetime.strptime(date, '%Y-%m-%d')
    max_shipped_date = datetime.strptime(date, '%Y-%m-%d') + timedelta(days=30)

    lineitem_scan = map(lambda p:
                        query_plan.add_operator(
                            tpch_q14.sql_scan_lineitem_operator_def(
                                lineitem_sharded,
                                p,
                                lineitem_parts,
                                use_pandas,
                                secure,
                                use_native,
                                'lineitem_scan' + '_' + str(p),
                                query_plan, sf, format_)),
                        range(0, lineitem_parts))

    lineitem_project = map(lambda p:
                           query_plan.add_operator(
                               tpch_q14.project_partkey_extendedprice_discount_shipdate_operator_def(
                                   'lineitem_project' + '_' + str(p),
                                   query_plan)),
                           range(0, lineitem_parts))

    part_scan = map(lambda p:
                    query_plan.add_operator(
                        tpch_q14.sql_scan_part_operator_def(
                            part_sharded,
                            p,
                            part_parts,
                            use_pandas,
                            secure,
                            use_native,
                            'part_scan' + '_' + str(p),
                            query_plan,
                            sf, format_)),
                    range(0, part_parts))

    part_project = map(lambda p:
                       query_plan.add_operator(
                           tpch_q14.project_partkey_brand_type_operator_def(
                               'part_project' + '_' + str(p),
                               query_plan)),
                       range(0, part_parts))

    lineitem_filter = map(lambda p:
                          query_plan.add_operator(
                              tpch_q14.filter_shipdate_operator_def(
                                  min_shipped_date,
                                  max_shipped_date,
                                  'lineitem_filter' + '_' + str(p),
                                  query_plan)),
                          range(0, lineitem_parts))

    lineitem_map = map(lambda p:
                       query_plan.add_operator(Map('l_partkey', 'lineitem_map' + '_' + str(p), query_plan, False)),
                       range(0, lineitem_parts))

    part_map = map(lambda p:
                   query_plan.add_operator(Map('p_partkey', 'part_map' + '_' + str(p), query_plan, False)),
                   range(0, part_parts))

    # part_filter = map(lambda p:
    #                   query_plan.add_operator(
    #                       tpch_q14.filter_brand12_operator_def('part_filter' + '_' + str(p), query_plan)),
    #                   range(0, part_parts))

    join_build = map(lambda p:
                     query_plan.add_operator(
                         HashJoinBuild('p_partkey', 'join_build' + '_' + str(p), query_plan, False)),
                     range(0, other_parts))

    join_probe = map(lambda p:
                     query_plan.add_operator(
                         HashJoinProbe(JoinExpression('p_partkey', 'l_partkey'), 'join_probe' + '_' + str(p),
                                       query_plan, False)),
                     range(0, other_parts))

    part_aggregate = map(lambda p:
                         query_plan.add_operator(
                             tpch_q14.aggregate_promo_revenue_operator_def(
                                 'part_aggregate' + '_' + str(p),
                                 query_plan)),
                         range(0, other_parts))

    def aggregate_reduce_fn(df):
        sum1_ = df['_0'].astype(np.float).sum()
        sum2_ = df['_1'].astype(np.float).sum()
        return pd.DataFrame({'_0': [sum1_], '_1': [sum2_]})

    aggregate_reduce = query_plan.add_operator(
        Aggregate(
            [
                AggregateExpression(AggregateExpression.SUM, lambda t: float(t['_0'])),
                AggregateExpression(AggregateExpression.SUM, lambda t: float(t['_1']))
            ],
            use_pandas,
            'aggregate_reduce',
            query_plan,
            False, aggregate_reduce_fn))

    aggregate_project = query_plan.add_operator(
        tpch_q14.project_promo_revenue_operator_def('aggregate_project', query_plan))

    collate = query_plan.add_operator(tpch_q14.collate_operator_def('collate', query_plan))

    # Inline what we can
    map(lambda o: o.set_async(False), lineitem_project)
    map(lambda o: o.set_async(False), part_project)
    map(lambda o: o.set_async(False), lineitem_filter)
    map(lambda o: o.set_async(False), part_map)
    map(lambda o: o.set_async(False), lineitem_map)
    map(lambda o: o.set_async(False), part_aggregate)
    aggregate_project.set_async(False)

    # Connect the operators
    connect_many_to_many(lineitem_scan, lineitem_project)
    connect_many_to_many(lineitem_project, lineitem_filter)
    connect_many_to_many(part_scan, part_project)
    connect_many_to_many(part_project, part_map)
    connect_all_to_all(part_map, join_build)
    connect_many_to_many(join_build, join_probe)
    connect_many_to_many(lineitem_filter, lineitem_map)
    connect_all_to_all(lineitem_map, join_probe)
    connect_many_to_many(join_probe, part_aggregate)
    connect_many_to_one(part_aggregate, aggregate_reduce)
    connect_one_to_one(aggregate_reduce, aggregate_project)
    connect_one_to_one(aggregate_project, collate)

    # Plan settings
    print('')
    print("Settings")
    print("--------")
    print('')
    print('use_pandas: {}'.format(use_pandas))
    print('secure: {}'.format(secure))
    print('use_native: {}'.format(use_native))
    print("lineitem parts: {}".format(lineitem_parts))
    print("part_parts: {}".format(part_parts))
    print("lineitem_sharded: {}".format(lineitem_sharded))
    print("part_sharded: {}".format(part_sharded))
    print("other_parts: {}".format(other_parts))
    print("format: {}".format(format_))
    print('')

    # Write the plan graph
    query_plan.write_graph(os.path.join(ROOT_DIR, "../benchmark-output"), gen_test_id() + "-" + str(lineitem_parts))

    # Start the query
    query_plan.execute()

    tuples = collate.tuples()

    collate.print_tuples(tuples)

    # Write the metrics
    query_plan.print_metrics()

    # Shut everything down
    query_plan.stop()

    field_names = ['promo_revenue']

    assert len(tuples) == 1 + 1

    assert tuples[0] == field_names

    # NOTE: This result has been verified with the equivalent data and query on PostgreSQL
    if s3filter.util.constants.TPCH_SF == 10:
        assert round(float(tuples[1][0]), 10) == 15.4488836202
    elif s3filter.util.constants.TPCH_SF == 1:
        numpy.testing.assert_approx_equal(float(tuples[1][0]), expected_result)


if __name__ == "__main__":
    main(1, 4, False, 4, False, 2, tpch_results.q14_sf1_expected_result, Format.PARQUET)
