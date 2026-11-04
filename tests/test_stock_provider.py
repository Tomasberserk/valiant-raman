"""Tests for StockVideoProvider (Pexels / Pixabay stock footage integration & caching)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from engine.media.stock_provider import StockVideoProvider
from engine.media.visuals import ProceduralVisualProvider, VisualProvider


def test_stock_provider_initialization_offline_safe():
    """Verify StockVideoProvider can be instantiated without API keys safely."""
    provider = StockVideoProvider(pexels_api_key=None, pixabay_api_key=None)
    assert provider.pexels_api_key is None
    assert provider.pixabay_api_key is None
    assert isinstance(provider.fallback_provider, ProceduralVisualProvider)


def test_stock_provider_fallback_when_no_keys(tmp_path: Path):
    """When no API keys are configured, provider delegates immediately to fallback."""
    mock_fallback = MagicMock(spec=VisualProvider)
    expected_out = tmp_path / "fallback_output.mp4"
    mock_fallback.generate_background.return_value = expected_out

    provider = StockVideoProvider(
        pexels_api_key=None,
        pixabay_api_key=None,
        fallback_provider=mock_fallback,
    )

    out_file = tmp_path / "output.mp4"
    res = provider.generate_background(
        output_path=out_file,
        duration_seconds=5.0,
        topic="tecnologia inteligencia artificial",
    )

    assert res == expected_out
    mock_fallback.generate_background.assert_called_once()
    call_kwargs = mock_fallback.generate_background.call_args[1]
    assert call_kwargs["duration_seconds"] == 5.0
    assert "tecnologia" in call_kwargs["topic"]


def test_stock_provider_pexels_search_and_caching(tmp_path: Path):
    """Test searching Pexels, downloading raw clip, normalizing to 9:16, and caching."""
    cache_dir = tmp_path / "cache"
    out_file = tmp_path / "final_stock.mp4"

    mock_pexels_response = {
        "videos": [
            {
                "id": 12345,
                "width": 1080,
                "height": 1920,
                "duration": 15,
                "video_files": [
                    {
                        "id": 999,
                        "quality": "hd",
                        "file_type": "video/mp4",
                        "width": 1080,
                        "height": 1920,
                        "link": "https://example.com/pexels_video_1080x1920.mp4",
                    }
                ],
            }
        ]
    }

    provider = StockVideoProvider(
        pexels_api_key="test_pexels_key",
        cache_dir=cache_dir,
    )

    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch.object(provider, "_download_file") as mock_download, \
         patch.object(provider, "_normalize_video_format") as mock_normalize:

        # Mock API response
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_pexels_response).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        def fake_download(url, dest):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("raw video bytes")
            return dest

        def fake_normalize(src, dest, duration, width, height, fps, codec):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("normalized video bytes")
            return dest

        mock_download.side_effect = fake_download
        mock_normalize.side_effect = fake_normalize

        res = provider.generate_background(
            output_path=out_file,
            duration_seconds=4.0,
            topic="deep space galaxy",
        )

        assert res.exists()
        assert mock_download.called
        assert mock_normalize.called


def test_stock_provider_cache_hit(tmp_path: Path):
    """Test that if an asset is already cached, no remote API calls are executed."""
    cache_dir = tmp_path / "cache"
    out_file = tmp_path / "cached_output.mp4"

    provider = StockVideoProvider(
        pexels_api_key="test_pexels_key",
        cache_dir=cache_dir,
    )

    # Pre-seed cache
    cache_key = provider._compute_cache_key("cyberpunk city", 6.0)
    cached_file = cache_dir / f"{cache_key}.mp4"
    cached_file.parent.mkdir(parents=True, exist_ok=True)
    cached_file.write_text("pre-existing cached video with enough bytes to exceed minimal threshold" * 5)

    with patch("urllib.request.urlopen") as mock_urlopen:
        res = provider.generate_background(
            output_path=out_file,
            duration_seconds=6.0,
            topic="cyberpunk city",
        )

        # urllib shouldn't be called because cache hit occurred
        mock_urlopen.assert_not_called()
        assert res.exists()
        assert "pre-existing cached video" in res.read_text()


def test_stock_provider_resilience_on_api_error(tmp_path: Path):
    """If Pexels returns 401 or network error, it falls back seamlessly to procedural provider."""
    mock_fallback = MagicMock(spec=VisualProvider)
    mock_fallback.generate_background.return_value = tmp_path / "fallback.mp4"

    provider = StockVideoProvider(
        pexels_api_key="invalid_or_expired_key",
        fallback_provider=mock_fallback,
    )

    with patch("urllib.request.urlopen", side_effect=Exception("HTTP 401 Unauthorized")):
        out_file = tmp_path / "output.mp4"
        res = provider.generate_background(
            output_path=out_file,
            duration_seconds=5.0,
            topic="ai neural networks",
        )

        assert mock_fallback.generate_background.called
        assert res == tmp_path / "fallback.mp4"
