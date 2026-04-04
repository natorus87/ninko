# Checkmk Module

Checkmk monitoring integration for hosts, services, alerts, and status diagnostics.

## Features
- List and filter hosts/services
- Query host/service status and details
- Retrieve active alerts/problems
- Search hosts and services by keyword

## Connection
Create a Checkmk connection in **Settings -> Modules -> Checkmk**.

Typical fields:
- `url` (site URL)
- `site` (Checkmk site name)
- `username`
- `CHECKMK_API_PASSWORD` or `CHECKMK_API_TOKEN`

## Main Tools
- `checkmk_get_hosts`
- `checkmk_get_services`
- `checkmk_get_host_status`
- `checkmk_get_service_status`
- `checkmk_get_alerts`
- `checkmk_search_hosts`
- `checkmk_search_services`

## Notes
- Use token auth where possible.
- Keep host/service naming conventions consistent for better search quality.
