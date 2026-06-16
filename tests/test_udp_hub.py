import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "wsjtx_udp_hub", ROOT / "wsjtx_udp_hub.py"
)
hub = importlib.util.module_from_spec(SPEC)
sys.modules["wsjtx_udp_hub"] = hub
SPEC.loader.exec_module(hub)


class FakeSocket:
    def __init__(self):
        self.sent = []

    def sendto(self, data, address):
        self.sent.append((data, address))


class UdpHubTests(unittest.TestCase):
    def test_parse_client_arg(self):
        client = hub.parse_client_arg("queue=127.0.0.1:2240:readonly")

        self.assertEqual("queue", client.name)
        self.assertEqual(("127.0.0.1", 2240), client.endpoint.address)
        self.assertEqual("readonly", client.mode)

    def test_wsjtx_packet_forwards_to_all_clients_and_learns_sender(self):
        sock = FakeSocket()
        clients = [
            hub.parse_client_arg("gridtracker=127.0.0.1:2238:control"),
            hub.parse_client_arg("queue=127.0.0.1:2240:readonly"),
        ]
        stats = hub.HubStats()

        hub.route_datagram(
            sock,
            b"decode",
            ("127.0.0.1", 55123),
            clients,
            hub.client_by_address(clients),
            stats,
        )

        self.assertEqual(("127.0.0.1", 55123), stats.last_wsjtx)
        self.assertEqual(
            [(b"decode", ("127.0.0.1", 2238)), (b"decode", ("127.0.0.1", 2240))],
            sock.sent,
        )

    def test_control_client_forwards_to_last_wsjtx(self):
        sock = FakeSocket()
        clients = [hub.parse_client_arg("gridtracker=127.0.0.1:2238:control")]
        stats = hub.HubStats(last_wsjtx=("127.0.0.1", 55123))

        hub.route_datagram(
            sock,
            b"configure",
            ("127.0.0.1", 2238),
            clients,
            hub.client_by_address(clients),
            stats,
        )

        self.assertEqual([(b"configure", ("127.0.0.1", 55123))], sock.sent)
        self.assertEqual(1, stats.forwarded_to_wsjtx)

    def test_readonly_client_control_is_dropped(self):
        sock = FakeSocket()
        clients = [hub.parse_client_arg("queue=127.0.0.1:2240:readonly")]
        stats = hub.HubStats(last_wsjtx=("127.0.0.1", 55123))

        hub.route_datagram(
            sock,
            b"configure",
            ("127.0.0.1", 2240),
            clients,
            hub.client_by_address(clients),
            stats,
        )

        self.assertEqual([], sock.sent)
        self.assertEqual(1, stats.dropped_readonly)


if __name__ == "__main__":
    unittest.main()
