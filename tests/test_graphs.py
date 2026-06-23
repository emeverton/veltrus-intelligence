import pytest
from unittest.mock import patch

from src.graphs.revenue_graph import (
    query_identity_ltv,
    query_revenue_by_channel,
    upsert_campaign_node,
    upsert_identity_node,
)


def test_upsert_identity_calls_cypher():
    with patch("src.graphs.revenue_graph.execute_cypher") as mock_cypher:
        mock_cypher.return_value = []
        upsert_identity_node("test-profile-id", is_known=False)
        assert mock_cypher.called
        call_args = mock_cypher.call_args[0][0]
        assert "test-profile-id" in call_args
        assert "Identity" in call_args


def test_upsert_campaign_calls_cypher():
    with patch("src.graphs.revenue_graph.execute_cypher") as mock_cypher:
        mock_cypher.return_value = []
        upsert_campaign_node("camp_001", "google_ads")
        assert mock_cypher.called


def test_query_revenue_by_channel_parses_rows():
    mock_rows = [
        {"channel": '"google_ads"', "conversions": "3", "total_revenue": "750.0"},
        {"channel": '"meta_ads"', "conversions": "1", "total_revenue": "250.0"},
    ]
    with patch("src.graphs.revenue_graph.execute_cypher", return_value=mock_rows):
        result = query_revenue_by_channel(model="linear")
    assert len(result) == 2
    assert result[0]["channel"] == "google_ads"
    assert result[0]["total_revenue"] == 750.0
    assert result[1]["conversions"] == 1


def test_query_identity_ltv_parses_rows():
    mock_rows = [
        {"identity_id": '"profile-abc"', "total_conversions": "2", "ltv": "1000.0"},
    ]
    with patch("src.graphs.revenue_graph.execute_cypher", return_value=mock_rows):
        result = query_identity_ltv(min_revenue=0.0)
    assert result[0]["identity_id"] == "profile-abc"
    assert result[0]["ltv"] == 1000.0


def test_empty_graph_returns_empty_list():
    with patch("src.graphs.revenue_graph.execute_cypher", return_value=[]):
        assert query_revenue_by_channel() == []
        assert query_identity_ltv() == []
