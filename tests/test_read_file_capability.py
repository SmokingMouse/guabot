from pathlib import Path

from guabot.capabilities import ReadFileCapability


def test_read_file_capability_reads_content(tmp_path) -> None:
    sample = tmp_path / "sample.txt"
    sample.write_text("hello file capability", encoding="utf-8")

    cap = ReadFileCapability()
    result = cap.invoke({"path": str(sample)})

    assert result["path"] == str(sample.resolve())
    assert result["truncated"] is False
    assert "hello file capability" in result["content"]

