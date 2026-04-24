"""
Mininet Test Topology for SDN Learning Switch Controller
=========================================================
Creates a simple network with 1 switch and 3 hosts, then
runs connectivity tests to validate the learning switch.

Requirements:
    - Mininet installed  (sudo apt install mininet)
    - Ryu controller running:  ryu-manager learning_switch.py

Run this script with:
    sudo python3 test_topology.py
"""

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.topo import SingleSwitchTopo
from mininet.log import setLogLevel, info
from mininet.cli import CLI
import time


def run_tests():
    """
    Build a single-switch topology with 3 hosts and run ping tests.

    Topology:
        h1 ─┐
        h2 ─┤── s1 ──(RemoteController on 127.0.0.1:6653)
        h3 ─┘
    """
    setLogLevel('info')

    info("\n" + "=" * 60 + "\n")
    info("  SDN Learning Switch — Mininet Test\n")
    info("=" * 60 + "\n\n")

    # ── Build topology ──────────────────────────────────────────
    topo = SingleSwitchTopo(k=3)   # 1 switch, 3 hosts

    net = Mininet(
        topo=topo,
        controller=lambda name: RemoteController(
            name,
            ip='127.0.0.1',
            port=6653           # Default Ryu OpenFlow port
        ),
        switch=OVSSwitch,
        autoSetMacs=True        # Assign readable MACs: 00:00:00:00:00:01, etc.
    )

    net.start()
    info("\n[+] Network started\n")

    # Give controller a moment to connect
    time.sleep(2)

    h1, h2, h3 = net.get('h1', 'h2', 'h3')

    info("\n--- Host Info ---\n")
    for host in [h1, h2, h3]:
        info(f"  {host.name}: MAC={host.MAC()}  IP={host.IP()}\n")

    # ── Test 1: Ping All ────────────────────────────────────────
    info("\n[TEST 1] Ping all hosts (first pass — expect some flooding)\n")
    net.pingAll()

    time.sleep(1)

    # ── Test 2: Ping All Again ──────────────────────────────────
    info("\n[TEST 2] Ping all hosts again (MACs learned — expect direct forwarding)\n")
    net.pingAll()

    # ── Test 3: Bandwidth Test ──────────────────────────────────
    info("\n[TEST 3] iperf bandwidth test: h1 → h2\n")
    net.iperf((h1, h2))

    # ── Test 4: Single Ping with output ─────────────────────────
    info("\n[TEST 4] Individual ping h1 → h3\n")
    result = h1.cmd('ping -c 3 ' + h3.IP())
    info(result)

    # ── Optional: Drop into interactive CLI ─────────────────────
    info("\n[+] Dropping into Mininet CLI (type 'exit' to quit)\n")
    CLI(net)

    net.stop()
    info("\n[+] Network stopped. Test complete.\n")


if __name__ == '__main__':
    run_tests()
