from scripts.demo import main


def test_offline_demo_runs_through_manual_package(tmp_path, capsys):
    outbox = tmp_path / "outbox"

    result = main(database_url="sqlite:///:memory:", outbox_dir=outbox)

    output = capsys.readouterr().out
    assert result == 0
    assert "1. Collecting one mocked job" in output
    assert "2. Analyzed and matched" in output
    assert "3. Preparing" in output
    assert "4. Approving" in output
    assert "5. Creating a local manual application package" in output
    package_dirs = [path for path in outbox.iterdir() if path.is_dir()]
    assert len(package_dirs) == 1
    assert (package_dirs[0] / "letter.txt").is_file()
    assert (package_dirs[0] / "job.txt").is_file()
    assert (package_dirs[0] / "README.txt").is_file()