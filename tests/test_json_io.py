import os
import stat
import subprocess
from concurrent.futures import ThreadPoolExecutor

from medbench.json_io import write_new


def test_write_new_preserves_directory_permissions_and_publishes_a_single_complete_file(tmp_path):
    # Use a regular child directory whose Windows ACL is inherited from this test's private temp root.
    folder = tmp_path / "shared"
    folder.mkdir()
    control = folder / "control"
    control.write_bytes(b"control")
    target = folder / "sheet"
    candidates = [bytes([n]) * 1024 for n in range(1, 5)]

    def publish(content):
        try:
            write_new(target, content)
            return content
        except FileExistsError:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        winners = [data for data in pool.map(publish, candidates) if data is not None]
    assert winners == [target.read_bytes()]
    assert set(folder.iterdir()) == {target, control}
    if os.name == "nt":
        commands = (
            "$parts = [System.Security.AccessControl.AccessControlSections]::Access; "
            "$a = (Get-Acl -LiteralPath $env:SHEET_CONTROL).GetSecurityDescriptorSddlForm($parts); "
            "$b = (Get-Acl -LiteralPath $env:SHEET_RESULT).GetSecurityDescriptorSddlForm($parts); "
            "if ($a -ne $b) { exit 1 }"
        )
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", commands], check=True,
                       env={**os.environ, "SHEET_CONTROL": str(control), "SHEET_RESULT": str(target)})
    else:
        assert stat.S_IMODE(control.stat().st_mode) == stat.S_IMODE(target.stat().st_mode)
