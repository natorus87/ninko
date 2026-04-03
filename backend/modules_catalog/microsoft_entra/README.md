# Microsoft Entra Module

Microsoft Entra ID (formerly Azure Active Directory) – Users, Groups, Applications, Devices via Microsoft Graph API.

## Features

- List and search users
- Get user details
- Create, disable, and manage users
- Reset user passwords
- List and manage groups
- Add/remove group members
- List registered applications
- List registered devices
- Create groups

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ENTRA_TENANT_ID` | Azure AD Tenant ID |
| `ENTRA_CLIENT_ID` | Application (client) ID |
| `ENTRA_CLIENT_SECRET` | Client secret (stored in Vault) |

### Connection Manager

Create a connection via the Ninko dashboard with:
- **Tenant ID**: Azure AD Tenant ID
- **Client ID**: Application ID
- **Client Secret**: Secret value

## Required API Permissions

The Entra app registration needs these Microsoft Graph permissions:
- `User.Read.All`
- `User.ReadWrite.All`
- `Group.Read.All`
- `Group.ReadWrite.All`
- `Directory.Read.All`
- `Application.Read.All`
- `Device.Read.All`

## Routing Keywords

- `entra`, `azure ad`, `azure ad`, `microsoft identity`
- `office 365`, `microsoft 365`, `o365`, `ms identity`

## API Endpoints

- `GET /api/microsoft_entra/health` – Health check
- `GET /api/microsoft_entra/status` – User/group/device counts

## Tools

| Tool | Description |
|------|-------------|
| `list_entra_users` | List all users |
| `search_entra_user` | Search user by name/email |
| `get_user_details` | Get user details |
| `list_entra_groups` | List all groups |
| `get_group_members` | Get group members |
| `list_entra_applications` | List applications |
| `list_entra_devices` | List devices |
| `create_entra_user` | Create user |
| `disable_entra_user` | Disable user |
| `reset_entra_user_password` | Reset password |
| `create_entra_group` | Create group |
| `add_user_to_group` | Add user to group |