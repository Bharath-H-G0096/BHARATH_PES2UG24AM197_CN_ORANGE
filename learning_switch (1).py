"""
SDN Learning Switch Controller - Built with Ryu Framework
==========================================================
Implements a Layer-2 learning switch that:
  1. Learns MAC addresses dynamically
  2. Installs flow rules for known destinations
  3. Floods packets for unknown destinations
  4. Supports flow table inspection

Requirements:
    pip install ryu

Run with:
    ryu-manager learning_switch.py

Test with Mininet:
    sudo mn --controller=remote --topo=single,3
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types
import logging


class LearningSwitch(app_manager.RyuApp):
    """
    A Ryu-based SDN Learning Switch Controller.

    The switch learns which MAC address is reachable via which port,
    then installs OpenFlow rules to forward traffic efficiently.
    For unknown destinations, it floods to all ports (except ingress).
    """

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(LearningSwitch, self).__init__(*args, **kwargs)

        # MAC address table: { datapath_id -> { mac_address -> port_number } }
        self.mac_to_port = {}

        # Flow rule idle/hard timeouts (seconds)
        self.FLOW_IDLE_TIMEOUT = 30
        self.FLOW_HARD_TIMEOUT = 120

        # Minimum flow priority for learned rules
        self.FLOW_PRIORITY = 10

        self.logger.setLevel(logging.INFO)
        self.logger.info("=" * 60)
        self.logger.info("  SDN Learning Switch Controller Started")
        self.logger.info("=" * 60)

    # ------------------------------------------------------------------ #
    #  Helper: Add a flow rule to the switch flow table
    # ------------------------------------------------------------------ #
    def add_flow(self, datapath, priority, match, actions,
                 idle_timeout=0, hard_timeout=0):
        """
        Install a flow entry into the switch's flow table.

        Args:
            datapath    : The switch object
            priority    : Rule priority (higher = matched first)
            match       : OFPMatch object describing packet fields
            actions     : List of OFPAction objects to apply
            idle_timeout: Remove rule after N seconds of inactivity
            hard_timeout: Remove rule after N seconds regardless of traffic
        """
        ofproto = datapath.ofproto
        parser  = datapath.ofproto_parser

        # Build an instruction: apply the given actions
        inst = [parser.OFPInstructionActions(
            ofproto.OFPIT_APPLY_ACTIONS, actions
        )]

        # Build the FlowMod message
        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout
        )

        datapath.send_msg(mod)

    # ------------------------------------------------------------------ #
    #  Event: Switch connects — install the table-miss flow entry
    # ------------------------------------------------------------------ #
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """
        Called when a switch connects to the controller.
        Installs a default (table-miss) flow: send all unmatched
        packets to the controller via PACKET_IN.
        """
        datapath = ev.msg.datapath
        ofproto  = datapath.ofproto
        parser   = datapath.ofproto_parser

        self.logger.info(
            "[Switch %016x] Connected — installing table-miss entry",
            datapath.id
        )

        # Match everything (empty match = wildcard all fields)
        match = parser.OFPMatch()

        # Action: send to controller with full packet buffer
        actions = [
            parser.OFPActionOutput(
                ofproto.OFPP_CONTROLLER,
                ofproto.OFPCML_NO_BUFFER   # send entire packet
            )
        ]

        # Priority 0 = lowest, so real rules take precedence
        self.add_flow(datapath, priority=0, match=match, actions=actions)

    # ------------------------------------------------------------------ #
    #  Event: PACKET_IN — core learning + forwarding logic
    # ------------------------------------------------------------------ #
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """
        Called every time the switch cannot match a packet to a flow rule.

        Steps:
          1. Parse the incoming packet to extract src/dst MAC addresses.
          2. Record: src_mac → in_port  (learning phase).
          3. Look up dst_mac in our table:
               - Found  → install a flow rule, forward directly.
               - Unknown → flood to all ports.
        """
        msg      = ev.msg
        datapath = msg.datapath
        ofproto  = datapath.ofproto
        parser   = datapath.ofproto_parser

        dpid    = datapath.id          # Datapath (switch) ID
        in_port = msg.match['in_port'] # Port the packet arrived on

        # ----- Parse packet -----
        pkt     = packet.Packet(msg.data)
        eth_pkt = pkt.get_protocol(ethernet.ethernet)

        if eth_pkt is None:
            return  # Not an Ethernet frame, ignore

        dst_mac = eth_pkt.dst
        src_mac = eth_pkt.src

        # Ignore LLDP frames (Link Layer Discovery Protocol)
        if eth_pkt.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        # ----- Step 1: Initialise table for this switch if needed -----
        if dpid not in self.mac_to_port:
            self.mac_to_port[dpid] = {}

        # ----- Step 2: LEARN — record src_mac → in_port -----
        if src_mac not in self.mac_to_port[dpid]:
            self.logger.info(
                "[Switch %016x] LEARNED  src=%s  port=%s",
                dpid, src_mac, in_port
            )
        self.mac_to_port[dpid][src_mac] = in_port

        # ----- Step 3: DECIDE — look up destination -----
        if dst_mac in self.mac_to_port[dpid]:
            # We know the port — forward directly
            out_port = self.mac_to_port[dpid][dst_mac]
            self.logger.info(
                "[Switch %016x] FORWARD  src=%s → dst=%s  out_port=%s",
                dpid, src_mac, dst_mac, out_port
            )

            # Install a flow rule so next packets skip the controller
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst_mac)
            actions = [parser.OFPActionOutput(out_port)]

            self.add_flow(
                datapath,
                priority=self.FLOW_PRIORITY,
                match=match,
                actions=actions,
                idle_timeout=self.FLOW_IDLE_TIMEOUT,
                hard_timeout=self.FLOW_HARD_TIMEOUT
            )
        else:
            # Unknown destination — flood
            out_port = ofproto.OFPP_FLOOD
            self.logger.info(
                "[Switch %016x] FLOOD    src=%s → dst=%s  (unknown dst)",
                dpid, src_mac, dst_mac
            )

        # ----- Step 4: Send the current packet out -----
        actions = [parser.OFPActionOutput(out_port)]

        # Use buffer_id if available to avoid re-sending the full payload
        if msg.buffer_id != ofproto.OFP_NO_BUFFER:
            out = parser.OFPPacketOut(
                datapath=datapath,
                buffer_id=msg.buffer_id,
                in_port=in_port,
                actions=actions,
                data=None
            )
        else:
            out = parser.OFPPacketOut(
                datapath=datapath,
                buffer_id=ofproto.OFP_NO_BUFFER,
                in_port=in_port,
                actions=actions,
                data=msg.data
            )

        datapath.send_msg(out)

    # ------------------------------------------------------------------ #
    #  Utility: Flow Table Inspection
    # ------------------------------------------------------------------ #
    def inspect_flow_table(self, datapath):
        """
        Request a dump of all flow entries from the switch.
        The response is handled in flow_stats_reply_handler().

        Call this method to trigger an inspection, e.g.:
            self.inspect_flow_table(datapath)
        """
        parser  = datapath.ofproto_parser
        ofproto = datapath.ofproto

        # Request all flows (table_id=OFPTT_ALL means every table)
        req = parser.OFPFlowStatsRequest(
            datapath,
            table_id=ofproto.OFPTT_ALL
        )
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):
        """
        Receives the flow table dump and logs all installed rules.
        Triggered by inspect_flow_table().
        """
        datapath = ev.msg.datapath
        flows    = ev.msg.body

        self.logger.info(
            "\n[Switch %016x] ===== FLOW TABLE (%d entries) =====",
            datapath.id, len(flows)
        )
        self.logger.info(
            "  %-6s  %-8s  %-20s  %-15s  %-10s  %-10s",
            "Table", "Priority", "Match", "Actions",
            "Pkts", "Bytes"
        )
        self.logger.info("  " + "-" * 75)

        for flow in sorted(flows, key=lambda f: f.priority, reverse=True):
            self.logger.info(
                "  %-6s  %-8s  %-20s  %-15s  %-10s  %-10s",
                flow.table_id,
                flow.priority,
                str(flow.match),
                str(flow.instructions),
                flow.packet_count,
                flow.byte_count
            )

        self.logger.info("  " + "=" * 75)

    # ------------------------------------------------------------------ #
    #  Utility: Print MAC address table (for debugging)
    # ------------------------------------------------------------------ #
    def print_mac_table(self):
        """Logs the current in-memory MAC address table."""
        self.logger.info("\n===== MAC ADDRESS TABLE =====")
        if not self.mac_to_port:
            self.logger.info("  (empty)")
            return
        for dpid, table in self.mac_to_port.items():
            self.logger.info("  Switch: %016x", dpid)
            for mac, port in table.items():
                self.logger.info("    %-20s  →  port %s", mac, port)
        self.logger.info("=" * 30)
