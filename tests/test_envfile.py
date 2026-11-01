"""Tests for the .env loader."""

import os

import envfile


def test_parse_env():
    text = """
# comment
HA_URL=http://ha:8123
export HA_TOKEN="abc def"
HA_ENTITY='sensor.x'
EMPTY=
NOTE=value # trailing comment
no equals sign
"""
    assert envfile.parse_env(text) == {
        "HA_URL": "http://ha:8123",
        "HA_TOKEN": "abc def",
        "HA_ENTITY": "sensor.x",
        "EMPTY": "",
        "NOTE": "value",
    }


def test_load_env_keeps_existing(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("A_SET=from_file\nB_NEW=from_file\n", encoding="utf-8")
    monkeypatch.setenv("A_SET", "from_env")
    monkeypatch.delenv("B_NEW", raising=False)
    envfile.load_env(path)
    assert os.environ["A_SET"] == "from_env"
    assert os.environ["B_NEW"] == "from_file"
    monkeypatch.delenv("B_NEW")


def test_missing_file_is_fine(tmp_path):
    assert envfile.load_env(tmp_path / "nope.env") == {}
