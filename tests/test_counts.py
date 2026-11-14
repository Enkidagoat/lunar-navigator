"""Assert the locked primary comparison counts from the ranking."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RANKING = ROOT / "data" / "comparison_rankings.json"


def test_primary_simultaneous_counts():
    data = json.loads(RANKING.read_text(encoding="utf-8"))
    rec = data["recommended_demo_comparison"]
    assert rec["window_id"] == "2028-01-01_14d"
    assert rec["higher_site"] == "DM2-358"
    assert rec["lower_site"] == "SITE07-1223"
    assert rec["higher_site_counts"]["simultaneous"] == 324
    assert rec["lower_site_counts"]["simultaneous"] == 237
