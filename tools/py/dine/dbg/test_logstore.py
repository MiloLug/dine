import tempfile
import unittest
from pathlib import Path

from dine.dbg.logstore import LogStore, render


class LogStoreTest(unittest.TestCase):
    def test_seq_select_mirror(self):
        with tempfile.TemporaryDirectory() as d:
            s = LogStore(Path(d))
            s.append("syslog", "line", "a")
            s.set_mark()
            s.append("cmd", "bt", "$ bt\n#0 main")
            s.append("event", "stopped", "stopped", location={})
            self.assertEqual(s.cursor, 3)
            self.assertEqual(s.mark, 1)
            self.assertEqual([e["seq"] for e in s.select(1)], [2, 3])
            self.assertEqual([e["seq"] for e in s.select(0, ("syslog", "event"))], [1, 3])
            s.close()
            self.assertEqual(len((Path(d) / "events.jsonl").read_text().splitlines()), 3)
            self.assertIn("#0 main", (Path(d) / "cmd.log").read_text())

    def test_render_truncates_multiline(self):
        ev = {"seq": 7, "ts": 0, "src": "cmd", "kind": "bt", "text": "\n".join(map(str, range(10)))}
        out = render(ev, 3)
        self.assertEqual(len(out), 5)
        self.assertIn("log show 7", out[-1])


if __name__ == "__main__":
    unittest.main()
