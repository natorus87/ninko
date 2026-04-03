# Microsoft Intune Module

Microsoft Intune MDM – Mobile Device Management, Policies, Apps, and Compliance via Microsoft Graph API.

## Features

- List managed devices (iOS, Android, Windows, macOS)
- Get device details and compliance status
- List configuration policies
- List compliance policies
- List managed applications
- Wipe devices (factory reset)
- Retire devices (remove from management)
- Sync devices (trigger check-in)
- Locate devices

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `INTUNE_TENANT_ID` | Azure AD Tenant ID |
| `INTUNE_CLIENT_ID` | Application (client) ID |
| `INTUNE_CLIENT_SECRET` | Client secret (stored in Vault) |

### Connection Manager

Create a connection via the Ninko dashboard with:
- **Tenant ID**: Azure AD Tenant ID
- **Client ID**: Application ID
- **Client Secret**: Secret value

## Required API Permissions

The Intune app registration needs these Microsoft Graph permissions:
- `DeviceManagementManagedDevices.Read.All`
- `DeviceManagementManagedDevices.ReadWrite.All`
- `DeviceManagementConfiguration.Read.All`
- `DeviceManagementConfiguration.ReadWrite.All`
- `DeviceManagementApps.Read.All`

## Routing Keywords

- `intune`, `mdm`, `mobile device`, `device management`
- `endpoint manager`, `mem`, `device compliance`, `device policy`

## Tools

| Tool | Description |
|------|-------------|
| `list_intune_devices` | List all managed devices |
| `get_intune_device` | Get device details |
| `list_intune_policies` | List configuration policies |
| `list_intune_compliance_policies` | List compliance policies |
| `list_intune_apps` | List managed apps |
| `get_intune_device_compliance` | Check device compliance |
| `wipe_intune_device` | Wipe device (factory reset) |
| `retire_intune_device` | Retire device |
| `sync_intune_device` | Trigger sync |
| `locate_intune_device` | Locate device |