from modules.analysis import calculate_intervals, compare_consumers, high_usage_alerts, summarize_periods


def test_consecutive_readings_and_unknown_first(sample_records):
    records = sample_records([("2024-01-01", 10), ("2024-02-01", 35)])
    _, intervals, issues = calculate_intervals(records)
    assert intervals.iloc[0].consumption_kwh == 25
    assert "First reading" in issues.iloc[0].issue


def test_sorts_readings_before_calculation(sample_records):
    records = sample_records([("2024-02-01", 35), ("2024-01-01", 10)])
    _, intervals, _ = calculate_intervals(records)
    assert intervals.iloc[0].consumption_kwh == 25
    assert intervals.iloc[0].start_date.isoformat() == "2024-01-01"


def test_decrease_is_possible_reset_and_interval_excluded(sample_records):
    records = sample_records([("2024-01-01", 100), ("2024-02-01", 150), ("2024-03-01", 20)])
    _, intervals, issues = calculate_intervals(records)
    assert intervals.valid.tolist() == [True, False]
    assert any("possible reset or rollover" in issue for issue in issues.issue)


def test_negative_value_is_flagged_and_excluded(sample_records):
    records = sample_records([("2024-01-01", 10), ("2024-02-01", -2), ("2024-03-01", 20)])
    _, intervals, issues = calculate_intervals(records)
    assert intervals.valid.tolist() == [False, False]
    assert "Negative cumulative reading" in issues.iloc[0].issue


def test_non_finite_value_is_flagged_and_excluded(sample_records):
    records = sample_records([("2024-01-01", 10), ("2024-02-01", float("inf"))])
    _, intervals, issues = calculate_intervals(records)
    assert not intervals.iloc[0].valid
    assert "Non-finite cumulative reading" in issues.iloc[0].issue


def test_malformed_imported_date_is_reported_without_crashing(sample_records):
    records = sample_records([("not-a-date", 10), ("2024-02-01", 20)])
    _, intervals, issues = calculate_intervals(records)
    assert not intervals.iloc[0].valid
    assert "Invalid or missing reading date" in issues.iloc[0].issue


def test_different_meters_never_mix(sample_records):
    records = sample_records([("2024-01-01", 10), ("2024-02-01", 25)], meter_id=1)
    records += sample_records([("2024-01-01", 700), ("2024-02-01", 900)], meter_id=2)
    _, intervals, _ = calculate_intervals(records)
    assert set(intervals.meter_id) == {1, 2}
    assert sorted(intervals.consumption_kwh.tolist()) == [15.0, 200.0]


def test_duplicate_meter_date_interval_is_excluded(sample_records):
    records = sample_records([("2024-01-01", 10), ("2024-02-01", 20), ("2024-02-01", 22)])
    _, intervals, issues = calculate_intervals(records)
    assert not intervals.valid.any()
    assert any("Duplicate meter/date" in issue for issue in issues.issue)


def test_exact_month_boundaries_allocate_year_transition(sample_records):
    records = sample_records([("2024-12-01", 100), ("2025-01-01", 125)])
    summary, _ = summarize_periods(records)
    assert summary.period.tolist() == ["2024-12"]
    assert summary.iloc[0].consumption_kwh == 25


def test_cross_month_interval_is_unallocated(sample_records):
    records = sample_records([("2024-01-15", 100), ("2024-02-15", 125)])
    summary, _ = summarize_periods(records)
    assert summary.iloc[0].period == "Unallocated (spanning)"
    assert summary.iloc[0].consumption_kwh == 0
    assert summary.iloc[0].unallocated_intervals == 1


def test_year_report_requires_year_boundary(sample_records):
    records = sample_records([("2024-01-01", 100), ("2025-01-01", 500)])
    summary, _ = summarize_periods(records, "year")
    assert summary.iloc[0].period == "2024"
    assert summary.iloc[0].consumption_kwh == 400


def test_year_report_aggregates_monthly_intervals_and_marks_complete(sample_records):
    readings = [(f"2024-{month:02d}-01", month * 100) for month in range(1, 13)]
    readings.append(("2025-01-01", 1300))
    summary, _ = summarize_periods(sample_records(readings), "year")
    year = summary[summary.period == "2024"].iloc[0]
    assert year.consumption_kwh == 1200
    assert year.valid_intervals == 12
    assert year.complete_period


def test_partial_year_is_reported_but_not_alerted(sample_records):
    readings = [(f"2025-{month:02d}-01", month * 100) for month in range(1, 12)]
    summary, _ = summarize_periods(sample_records(readings), "year")
    year = summary[summary.period == "2025"].iloc[0]
    assert year.consumption_kwh == 1000
    assert not year.complete_period
    assert "Incomplete" in year.status
    assert high_usage_alerts(summary, 100).empty


def test_invalid_interval_is_visible_but_excluded_from_period_total(sample_records):
    records = sample_records([("2024-01-01", 100), ("2024-02-01", 300), ("2024-03-01", 50)])
    summary, _ = summarize_periods(records)
    allocated = summary[summary.valid_intervals > 0]
    invalid = summary[summary.period == "Invalid interval"]
    assert allocated.consumption_kwh.sum() == 200
    assert invalid.iloc[0].consumption_kwh == 0
    assert invalid.iloc[0].invalid_intervals == 1


def test_multi_year_spanning_interval_is_unallocated(sample_records):
    records = sample_records([("2023-01-01", 100), ("2025-01-01", 900)])
    summary, _ = summarize_periods(records, "year")
    assert summary.iloc[0].period == "Unallocated (spanning)"
    assert summary.iloc[0].consumption_kwh == 0
    assert summary.iloc[0].unallocated_intervals == 1


def test_consumer_comparison_includes_only_complete_allocated_periods(sample_records):
    first = sample_records([(f"2024-{month:02d}-01", month * 100) for month in range(1, 13)] + [("2025-01-01", 1300)], meter_id=1)
    second = sample_records([("2024-01-01", 0), ("2024-02-01", 300)], meter_id=2)
    third = sample_records([("2024-01-15", 0), ("2024-02-15", 900)], meter_id=3)
    records = first + second + third
    for row in records:
        if row["meter_id"] == 2:
            row["consumer_id"] = 2
            row["consumer_type"] = "Commercial"
        elif row["meter_id"] == 3:
            row["consumer_id"] = 3
            row["consumer_type"] = "Office"
    summary, _ = summarize_periods(records, "year")
    comparison = compare_consumers(summary, "2024")
    assert comparison.consumer_id.tolist() == [1]
    assert comparison.iloc[0].consumption_kwh == 1200


def test_high_usage_respects_threshold_and_partial_periods(sample_records):
    aligned = sample_records([("2024-01-01", 0), ("2024-02-01", 250)])
    summary, _ = summarize_periods(aligned)
    alerts = high_usage_alerts(summary, 100)
    assert alerts.iloc[0].excess_kwh == 150
    at_threshold = sample_records([("2024-01-01", 0), ("2024-02-01", 100)])
    at_threshold_summary, _ = summarize_periods(at_threshold)
    assert high_usage_alerts(at_threshold_summary, 100).empty
    partial = sample_records([("2024-01-02", 0), ("2024-02-01", 250)])
    partial_summary, _ = summarize_periods(partial)
    assert high_usage_alerts(partial_summary, 100).empty