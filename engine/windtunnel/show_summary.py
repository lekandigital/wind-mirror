"""Print the parts of a trust-experiment summary.json that matter, compactly."""
import sys, json
S = json.load(open(sys.argv[1]))
def p(k, v): print(f'{k}: {json.dumps(v)[:520]}')
for k in ['n_total', 'n_train', 'n_cal', 'n_test', 'n_ood', 'solver_seconds_median', 'solver_half_to_half_diff_median_pct', 'baseline_area_times_const', 'model_pair', 'model_5',
          'target_ranges_test', 'inference_ms_per_check_cpu_1thread', 'inference_ms_per_1000_checks_cpu_1thread', 'tau', 'signal_quality_on_test_plus_ood', 'learning_curve', 'flywheel', 'performer_clip']:
    if k in S: p(k, S[k])
for k, v in S['gate'].items():
    if v: print(f"gate.{k}: n={v['n']} instant={v['answered_instantly_pct']:.0f}% err_answered={v['err_of_answered_mean_pct']} within_tol={v.get('answered_within_tol_pct')} max_answered={v.get('err_of_answered_max_pct')} err_escalated={v['err_of_escalated_mean_pct']} no_gate_mean={v['err_if_no_gate_mean_pct']:.1f} max={v['err_if_no_gate_max_pct']:.1f} bad>10%: {v['bad_answers_gt10pct_total']} let through {v['bad_answers_gt10pct_let_through']}")
