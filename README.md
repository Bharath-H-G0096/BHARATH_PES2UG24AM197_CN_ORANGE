# SDN Learning Switch Controller

## Project Overview
This project implements a Software Defined Networking (SDN) Learning Switch Controller using the Ryu framework and OpenFlow protocol. The controller mimics the behavior of a traditional Layer-2 learning switch by dynamically learning MAC addresses and installing forwarding rules in the switch flow table.

## Problem Statement
Design and implement an SDN controller that:
- Learns source MAC addresses dynamically
- Maintains MAC-to-port mappings
- Installs flow rules for efficient forwarding
- Floods packets when destination MAC is unknown
- Supports flow table inspection and validation

## Features
- Dynamic MAC Address Learning
- Reactive Flow Rule Installation
- Packet Forwarding Validation
- Flow Table Inspection
- Unknown Destination Flooding
- OpenFlow-Based Forwarding Control

## Technologies Used
- Python
- Ryu SDN Controller
- Mininet
- Open vSwitch
- OpenFlow 1.3

## Project Architecture
Workflow:

1. A packet arrives at the OpenFlow switch.
2. If no matching rule exists, switch sends Packet-In to controller.
3. Controller learns:
   Source MAC → Incoming Port
4. Controller checks destination MAC:
   - Known destination → installs forwarding rule
   - Unknown destination → floods packet
5. Future packets are forwarded directly by the switch.

## Code Implementation Overview

### MAC Learning Logic
The controller stores MAC-to-port mappings:

```python
self.mac_to_port[dpid][src_mac] = in_port
```

Example:

```text
00:00:00:00:00:01 -> Port 1
00:00:00:00:00:02 -> Port 2
```

---

### Destination Lookup and Forwarding

```python
if dst_mac in self.mac_to_port[dpid]:
    out_port = self.mac_to_port[dpid][dst_mac]
else:
    out_port = OFPP_FLOOD
```

- Known destination:
Forward directly

- Unknown destination:
Flood packet

---

### Dynamic Flow Rule Installation

```python
match = parser.OFPMatch(
    in_port=in_port,
    eth_dst=dst_mac
)
```

Controller installs flow rules using Flow-Mod messages so future packets bypass the controller.

---

### Flow Table Inspection

```bash
sudo ovs-ofctl dump-flows s1
```

Used to verify installed OpenFlow entries.

## Files Included
- learning_switch.py  
Main SDN controller implementation

- test_topology.py  
Mininet topology setup and testing

- README.md  
Project documentation

## Installation

```bash
sudo apt update
sudo apt install mininet openvswitch-switch
pip3 install ryu
```

## Running the Project

Run controller:

```bash
ryu-manager learning_switch.py
```

Run topology:

```bash
sudo python3 test_topology.py
```

Alternative:

```bash
sudo mn --controller=remote --topo=single,3
```

## Validation
Project is validated using:

- pingall connectivity tests  
- Dynamic packet forwarding checks  
- Flow table inspection  
- iperf bandwidth test

## Expected Outcomes
- Correct MAC learning behavior
- Efficient forwarding after learning
- Reduced controller intervention
- Proper OpenFlow rule installation

## Future Enhancements
- Shortest-path forwarding
- Load balancing
- Security policy enforcement
- Traffic monitoring

## Author
Bharath H G
