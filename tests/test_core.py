import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd, pytest
from modules import analytics_engine as AE, ranking_engine as RE, keyword_engine as KE, fiverr_mcp as FM
from modules.seo_engine import audit_account, WEIGHTS
from modules.strategy_engine import build_plans


@pytest.fixture(scope="module")
def acct():
    return FM.load_account("sohagjone", prefer_live=False)


def test_weights_sum_to_100():
    assert sum(WEIGHTS.values()) == 100


def test_snapshot_loads(acct):
    assert acct["source"] == "snapshot" and len(acct["gigs"]) == 8 and acct["profile"]["rating"]["count"] == 68


def test_scores_bounded_and_flagged(acct):
    for a in audit_account(acct, {}):
        assert 0 <= a["total"] <= 100 and a["projected"] >= a["total"]
        assert a["confidence"] < 1  # tags/category unknown without manual metadata


def test_metadata_raises_confidence(acct):
    g = acct["gigs"][6]
    base = audit_account(acct, {})[6]
    meta = {g["slug"]: {"tags": "n8n automation, pdf invoice, google sheets, invoice data extraction, n8n expert", "category": "Programming & Tech", "subcategory": "Automation", "faq_count": 4, "requirements_count": 2}}
    after = audit_account(acct, meta)[6]
    assert after["confidence"] > base["confidence"]


def test_readonly_guard():
    with pytest.raises(FM.MCPError):
        FM.FiverrMCPClient().call_tool("wp_delete_post", {})


def test_parse_tool_text_with_prefix():
    assert FM.parse_tool_text('Found 2 sellers: a, b{"sellers":[1,2]}')["sellers"] == [1, 2]


def test_ctr_and_zero_denominator():
    df = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=2), "gig": "g", "impressions": [100, 0], "clicks": [5, 0], "orders": [1, 0], "revenue": [20, 0]})
    r = AE.add_rates(df)
    assert r["ctr"].iloc[0] == 5.0 and np.isnan(r["ctr"].iloc[1]) and np.isnan(r["aov"].iloc[1])


def test_trend_needs_enough_data():
    df = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=10), "gig": "g", "impressions": 10, "clicks": 1, "orders": 0, "revenue": 0})
    assert AE.trend(df, "impressions")["direction"] == "Insufficient data"


def test_missing_required_mapping():
    with pytest.raises(ValueError):
        AE.normalise(pd.DataFrame({"a": [1]}), {"date": None, "impressions": None, "clicks": None})


def test_ranking_validation_and_not_available():
    assert RE.validate("", "x", None, None)
    rows = pd.DataFrame([RE.make_row("g", "kw", None, None, "", "", "", "")])
    assert RE.summarize(rows)["Latest position"].iloc[0] == "Not Available"


def test_keywords_have_honest_competition_label(acct):
    df = KE.generate("n8n automation", "", [])
    assert (df["Competition evidence"].str.startswith("Not measured")).all() and len(df) > 10


def test_plans_have_all_horizons(acct):
    p = build_plans(acct, audit_account(acct, {}))
    assert set(p) == {7, 30, 60, 90} and all(len(v) for v in p.values())
