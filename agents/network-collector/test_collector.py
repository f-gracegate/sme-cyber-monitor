"""Parser and pipeline tests for the network collector. Run: python -m unittest discover agents"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import smecm_collector as c  # noqa: E402


def one(events):
    assert len(events) == 1, events
    return events[0]


class SyslogParsing(unittest.TestCase):
    def test_fortigate(self):
        deny = one(c.parse_syslog(
            '<189>date=2026-11-26 devname="FW1" logid="0000000013" type="traffic" '
            'subtype="forward" srcip=203.0.113.5 dstip=192.168.1.10 dstport=3389 proto=6 '
            'action="deny"', "192.168.1.1"))
        self.assertEqual(deny["event_type"], "network.firewall_deny")
        self.assertEqual(deny["device"], "FW1")
        self.assertEqual(deny["data"]["dst_port"], "3389")
        change = one(c.parse_syslog(
            '<189>logid="0100044547" type="event" subtype="system" user="admin" action="edit" '
            'logdesc="Configuration changed"', "192.168.1.1"))
        self.assertEqual(change["event_type"], "network.config_change")
        fail = one(c.parse_syslog(
            '<189>logid="0100032002" type="event" subtype="system" user="admin" '
            'srcip=198.51.100.9 logdesc="Admin login failed"', "192.168.1.1"))
        self.assertEqual(fail["event_type"], "network.admin_login_failure")
        allowed = c.parse_syslog('<189>logid="1" type="traffic" action="accept" srcip=1.1.1.1',
                                 "192.168.1.1")
        self.assertEqual(allowed, [])  # allowed traffic is never forwarded

    def test_cisco_asa(self):
        deny = one(c.parse_syslog("<164>%ASA-4-106023: Deny tcp src outside:203.0.113.5/51234 "
                                  "dst inside:10.0.0.5/22 by access-group", "10.0.0.1"))
        self.assertEqual(deny["data"]["src_ip"], "203.0.113.5")
        self.assertEqual(deny["data"]["dst_port"], "22")
        change = one(c.parse_syslog("<165>%ASA-5-111010: User 'admin', running 'CLI' from IP "
                                    "10.0.0.9, executed 'access-list x'", "10.0.0.1"))
        self.assertEqual(change["event_type"], "network.config_change")

    def test_pfsense_filterlog(self):
        line = ("<134>filterlog[123]: 5,,,1000000103,igb1,match,block,in,4,0x0,,64,0,0,DF,6,tcp,"
                "60,203.0.113.5,192.168.1.10,51234,22,0,S,1,,64240,,mss")
        deny = one(c.parse_syslog(line, "192.168.1.1"))
        self.assertEqual(deny["data"], {"src_ip": "203.0.113.5", "dst_ip": "192.168.1.10",
                                        "dst_port": "22", "proto": "tcp"})
        passed = line.replace(",block,", ",pass,")
        self.assertEqual(c.parse_syslog(passed, "192.168.1.1"), [])

    def test_iptables_and_mikrotik(self):
        deny = one(c.parse_syslog("<4>kernel: [UFW BLOCK] IN=eth0 OUT= SRC=203.0.113.66 "
                                  "DST=192.168.1.1 PROTO=TCP SPT=5 DPT=23", "192.168.1.1"))
        self.assertEqual(deny["data"]["dst_port"], "23")
        fail = one(c.parse_syslog("system,error,critical login failure for user admin from "
                                  "198.51.100.4 via winbox", "192.168.88.1"))
        self.assertEqual(fail["data"]["user"], "admin")
        change = one(c.parse_syslog("system,info filter rule changed by admin", "192.168.88.1"))
        self.assertEqual(change["event_type"], "network.config_change")

    def test_garbage_is_ignored(self):
        self.assertEqual(c.parse_syslog("", "1.2.3.4"), [])
        self.assertEqual(c.parse_syslog("<13>hello world", "1.2.3.4"), [])


class Sensors(unittest.TestCase):
    def test_suricata_alert(self):
        e = one(c.parse_suricata(c.SURICATA_SAMPLE))
        self.assertEqual(e["event_type"], "network.ids_alert")
        self.assertEqual(e["severity"], "high")
        self.assertEqual(e["device"], "192.168.1.25")  # the internal host involved
        self.assertTrue(e["timestamp"].startswith("2026-11-26T10:00:00"))
        self.assertEqual(c.parse_suricata(json.dumps({"event_type": "flow"})), [])
        self.assertEqual(c.parse_suricata("not json"), [])

    def test_zeek_tsv_and_json(self):
        reader = c.ZeekReader()
        self.assertEqual(reader.records("#fields\tts\tnote\tmsg\tsrc\tdst"), [])
        recs = reader.records("1732615200.0\tScan::Port_Scan\t192.168.1.40 scanned 50 ports\t"
                              "192.168.1.40\t-")
        e = one(c.parse_zeek_notice(recs[0]))
        self.assertEqual(e["data"]["note"], "Scan::Port_Scan")
        self.assertEqual(e["device"], "192.168.1.40")
        json_rec = c.ZeekReader().records(json.dumps({"ts": 1732615200.0, "note": "SSH::Password_Guessing", "src": "203.0.113.1"}))
        self.assertEqual(one(c.parse_zeek_notice(json_rec[0]))["data"]["note"],
                         "SSH::Password_Guessing")

    def test_traffic_summary(self):
        stats = c.TrafficStats()
        self.assertIsNone(stats.snapshot())
        stats.add_conn({"id.orig_h": "192.168.1.5", "orig_bytes": "100", "resp_bytes": "900"})
        stats.add_conn({"id.orig_h": "8.8.8.8", "orig_bytes": "-", "resp_bytes": "10"})
        snap = stats.snapshot()
        self.assertEqual((snap["connections"], snap["bytes_out"], snap["bytes_in"]), (2, 100, 910))
        self.assertEqual(snap["top_talkers"], [{"host": "192.168.1.5", "bytes": 1000}])


class Probing(unittest.TestCase):
    def test_probe_plan(self):
        self.assertEqual(c.probe_plan("192.168.1.1"), ("192.168.1.1", c.PROBE_PORTS))
        host, ports = c.probe_plan("https://fw.local:4443/admin")
        self.assertEqual((host, ports[0]), ("fw.local", 4443))
        host, ports = c.probe_plan("[fd00::1]:8443")
        self.assertEqual((host, ports[0]), ("fd00::1", 8443))
        self.assertEqual(c.probe_plan("fd00::1")[0], "fd00::1")


class PipelineBehaviour(unittest.TestCase):
    def test_denies_are_aggregated(self):
        p = c.Pipeline()
        line = ("<4>kernel: [UFW BLOCK] IN=eth0 OUT= SRC=203.0.113.66 DST=192.168.1.1 "
                "PROTO=TCP SPT=5 DPT=23")
        for _ in range(250):
            p.add(c.parse_syslog(line, "192.168.1.1"))
        p.roll_aggregates(force=True)
        batch = p.take(10)
        self.assertEqual(len(batch), 1)
        self.assertEqual(batch[0]["count"], 250)

    def test_queue_is_bounded(self):
        p = c.Pipeline()
        original = c.MAX_QUEUE
        c.MAX_QUEUE = 3
        try:
            p.add([c._event("network.config_change", "d", f"x{i}", {}) for i in range(5)])
        finally:
            c.MAX_QUEUE = original
        self.assertEqual(len(p.queue), 3)
        self.assertEqual(p.counters()[0], 2)

    def test_spool_survives_restart(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "collector.json"
            first = c.Collector({"server": "https://x"}, path)
            first.pipeline.add([c._event("network.config_change", "d", "x", {})])
            first.save_spool()
            second = c.Collector({"server": "https://x"}, path)
            second.pipeline.restore(c.load_json(second.spool_path, []))
            self.assertEqual(len(second.pipeline.queue), 1)

    def test_only_approved_networks_may_send_syslog(self):
        col = c.Collector({"server": "https://x", "allowed_sources": ["192.168.1.0/24"]},
                          Path("/tmp/none.json"))
        col.handle_syslog("<134>%ASA-5-111010: User 'a' executed 'x'", "203.0.113.9")
        col.handle_syslog("<134>%ASA-5-111010: User 'a' executed 'x'", "192.168.1.1")
        self.assertEqual(len(col.pipeline.queue), 1)


if __name__ == "__main__":
    unittest.main()
