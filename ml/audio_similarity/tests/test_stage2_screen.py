import copy
import numpy as np
import pandas as pd

from audio_similarity.stage2_screen import (component_metrics, family_decisions,
    query_bootstrap, query_macro_accuracy, rescue_stats, score_table, write_outputs)


def _rows():
    return pd.DataFrame([
      {"query_track_id":1,"canonical_label":"A","b":1.,"r":-1.},
      {"query_track_id":1,"canonical_label":"B","b":1.,"r":-1.},
      {"query_track_id":2,"canonical_label":"A","b":0.,"r":1.},
    ])


def test_query_macro_accuracy_and_exact_score_tie_half_credit():
    # q1 credits 1,0 -> .5; q2 exact tie -> .5; macro=.5
    assert query_macro_accuracy(_rows(), "b") == .5


def test_rescue_conflict_and_net_rescue_math():
    stats = rescue_stats(_rows(), "b", "r")
    assert stats["disagreement_count"] == 3
    assert stats["rescue_count"] == 2
    assert stats["conflict_count"] == 1
    assert stats["net_rescue"] == 1


def test_query_cluster_bootstrap_is_deterministic():
    effects = {"1": -.25, "2": .5, "9": 1.0}
    assert query_bootstrap(effects, 1000, 42) == query_bootstrap(effects, 1000, 42)


def test_margin_orientation_survives_ab_randomization():
    original = pd.DataFrame([{"query_track_id":1,"canonical_label":"A","base_sim_a":.8,"base_sim_b":.2,
                              "x_sim_a":.7,"x_sim_b":.1}])
    swapped = pd.DataFrame([{"query_track_id":1,"canonical_label":"B","base_sim_a":.2,"base_sim_b":.8,
                             "x_sim_a":.1,"x_sim_b":.7}])
    a = component_metrics(original, "base", "x", 100, 1)
    b = component_metrics(swapped, "base", "x", 100, 1)
    assert a["baseline_accuracy"] == b["baseline_accuracy"] == 1.0
    assert a["residual_accuracy"] == b["residual_accuracy"] == 1.0


def _gate_metrics(net1=1, net2=1, disagreements=10, probability=.8, direct1=0, direct2=0):
    def m(net, direct):
        p={"net_rescue":net,"disagreement_count":disagreements,"bootstrap_probability_net_rescue_positive":probability}
        return {"primary":p,"direct_disagreement":{"net_rescue":direct}}
    return {"x":{"clap":m(net1,direct1),"mert":m(net2,direct2)}}


def _gate_cfg():
    return {"components":{"family":["x"]},"active_baselines":["clap","mert"],
            "decision":{"min_disagreements_each_baseline":10,"min_positive_probability":.8}}


def test_exact_promising_gate_boundary():
    assert family_decisions(_gate_metrics(), _gate_cfg())["family"]["status"] == "PROMISING_FOR_STAGE_2B"
    assert family_decisions(_gate_metrics(disagreements=9), _gate_cfg())["family"]["status"] == "INCONCLUSIVE"
    assert family_decisions(_gate_metrics(probability=.799), _gate_cfg())["family"]["status"] == "INCONCLUSIVE"
    assert family_decisions(_gate_metrics(direct1=-1), _gate_cfg())["family"]["status"] == "INCONCLUSIVE"


def test_exact_no_signal_and_inconclusive_boundaries():
    assert family_decisions(_gate_metrics(net1=0,net2=0), _gate_cfg())["family"]["status"] == "NO_SIGNAL"
    assert family_decisions(_gate_metrics(net1=1,net2=0), _gate_cfg())["family"]["status"] == "INCONCLUSIVE"


def test_slices_keep_ab_primary_and_tie_neither_anchor_diagnostics_network_free():
    rows=[]
    for i,(sl,label,eligible) in enumerate([
        ("direct_disagreement","A",True),("competitive_rank2","B",True),
        ("anchor_negative","A",False),("direct_disagreement","Tie",False),
        ("competitive_rank2","Neither",False)]):
        row={"query_track_id":i+1,"slice":sl,"canonical_label":label,"label_status":"CANONICAL",
             "primary_eligible":eligible,"raw_judgment_count":1}
        for base in ("clap","mert"):
            row[f"{base}_sim_a"],row[f"{base}_sim_b"]=.8,.2
        row["x_sim_a"],row["x_sim_b"]=.7,.3
        rows.append(row)
    cfg={"experiment_id":"fixture","seed":3,"active_baselines":["clap","mert"],
         "components":{"family":["x"]},"bootstrap":{"count":100},
         "decision":{"min_disagreements_each_baseline":10,"min_positive_probability":.8}}
    result=score_table(pd.DataFrame(rows),cfg)
    assert result["denominators"] == {"canonical_trials":5,"raw_judgments":5,"primary_ab":2,
      "direct_disagreement_ab":1,"anchor_ab":1,"tie":1,"neither":1,"rater_conflict":0}


def test_end_to_end_fixture_writes_deterministic_artifacts_without_network(tmp_path):
    table = pd.DataFrame([{"trial_id":"1:H1","query_track_id":1,"slice":"direct_disagreement",
        "canonical_label":"A","label_status":"CANONICAL","primary_eligible":True,"raw_judgment_count":1,
        "clap_sim_a":.8,"clap_sim_b":.2,"mert_sim_a":.7,"mert_sim_b":.3,"x_sim_a":.9,"x_sim_b":.1}])
    cfg={"experiment_id":"fixture","seed":3,"active_baselines":["clap","mert"],
         "components":{"family":["x"]},"diagnostics":[],"bootstrap":{"count":100},
         "decision":{"min_disagreements_each_baseline":10,"min_positive_probability":.8},
         "paths":{"report_dir":"out"},"excerpt":{"strategy":"center5_v1"}}
    result=score_table(table,cfg)
    first=write_outputs(table,[{"v":"A"}],result,cfg,tmp_path,{"ratings":"hash"})
    second=write_outputs(table,[{"v":"A"}],result,cfg,tmp_path,{"ratings":"hash"})
    assert first == second
    assert {p.name for p in (tmp_path/"out").iterdir()} == {
        "canonical_trial_features.csv","metrics.json","decision_report.md","input_provenance_manifest.json"}
