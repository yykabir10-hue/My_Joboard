"""Static checks on the portal-skill CLI contract.

These run offline against the source of every portal CLI. Live portal calls
deliberately stay out of the test suite (see .github/workflows/ci.yml) - these
assert properties that can be checked from the code itself.
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_FILES = sorted(REPO_ROOT.glob(".agents/skills/*/cli/src/cli.ts"))


def code_lines(path):
    """Source lines with `//` comments dropped, so prose cannot trip a check."""
    return [line for line in path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("//")]


class PortalCliFilesExist(unittest.TestCase):
    def test_there_are_portal_clis_to_check(self):
        self.assertTrue(CLI_FILES, "no portal cli.ts files found")


class StdoutIsNeverTruncated(unittest.TestCase):
    """No portal CLI may call process.exit().

    When stdout is a pipe, writes are asynchronous. Calling process.exit()
    discards whatever has not drained, silently truncating output at the 64KB
    pipe buffer - observed live as freehire-search returning 65536 bytes to a
    pipe where a file redirect got the full 89587. It is invisible interactively
    (TTY writes are synchronous) and invisible with `>` (so are file writes), so
    it only surfaces under automation, where it corrupts the day's whole pool.

    Use `process.exitCode = code` instead and let the runtime flush and exit.
    """

    def test_no_cli_calls_process_exit(self):
        for path in CLI_FILES:
            with self.subTest(portal=path.parts[-4]):
                offenders = [line.strip() for line in code_lines(path)
                             if "process.exit(" in line]
                self.assertEqual(
                    offenders, [],
                    "use `process.exitCode = ...`; process.exit() truncates "
                    "piped stdout at 64KB",
                )

    def test_hand_rolled_clis_still_set_an_exit_code(self):
        # Dropping process.exit() must not mean dropping the exit status - the
        # portal contract requires exit 1 on error.
        #
        # Scoped to hand-rolled entrypoints: a CLI built on a framework
        # (`createCLI(...).run()`, as the Danish demo portals are) lets the
        # framework own its exit status and never touches process.exitCode.
        for path in CLI_FILES:
            lines = code_lines(path)
            if not any("main()" in line for line in lines):
                continue
            with self.subTest(portal=path.parts[-4]):
                self.assertTrue(
                    any("process.exitCode" in line for line in lines),
                    "hand-rolled CLI sets no exit code at all",
                )


if __name__ == "__main__":
    unittest.main()
