"""Tests for the persistent user registry."""

from televoica.bot.registry import UserRegistry


def test_add_persists_across_instances(tmp_path):
    path = tmp_path / "state" / "users.json"
    registry = UserRegistry(path)
    assert registry.add(1) is True
    assert registry.add(1) is False
    registry.add(2)

    assert UserRegistry(path).chat_ids == {1, 2}


def test_remove_and_recipients(tmp_path):
    registry = UserRegistry(tmp_path / "users.json")
    registry.add(1)
    registry.add(2)
    registry.remove(1)
    registry.remove(99)  # unknown chat is a no-op

    assert registry.recipients(extra=[2, 3]) == {2, 3}


def test_last_announced_version_persists(tmp_path):
    path = tmp_path / "users.json"
    registry = UserRegistry(path)
    assert registry.last_announced_version is None
    registry.mark_announced("0.2.0")

    assert UserRegistry(path).last_announced_version == "0.2.0"


def test_corrupt_file_starts_empty(tmp_path):
    path = tmp_path / "users.json"
    path.write_text("{not json")

    registry = UserRegistry(path)
    assert registry.chat_ids == set()
    assert registry.add(5) is True
    assert UserRegistry(path).chat_ids == {5}
