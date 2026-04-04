# OPNsense Module

Firewall management and monitoring via OPNsense REST API.

## Features
- System/interface/gateway status
- Firewall and NAT rule read/write operations
- DHCP lease visibility
- Service restart and logs

## Connection
Configure in **Settings -> Modules -> OPNsense**.

Required:
- `host`
- `OPNSENSE_API_KEY`
- `OPNSENSE_API_SECRET`

Optional:
- TLS verify override per connection (for self-signed environments)

## Main Tools
- `get_opnsense_system_status`
- `get_opnsense_interfaces`, `get_opnsense_gateways`
- `get_opnsense_firewall_rules`, `create_opnsense_firewall_rule`, `delete_opnsense_firewall_rule`
- `get_opnsense_nat_rules`, `create_opnsense_nat_rule`, `delete_opnsense_nat_rule`
- `get_opnsense_services`, `restart_opnsense_service`
- `get_opnsense_dhcp_leases`, `get_opnsense_logs`

## Safety
- Rule create/delete operations are high-impact and should use Safeguard + operation journal tracking.
