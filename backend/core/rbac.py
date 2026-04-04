"""
RBAC store for users, groups, roles and module permissions.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from core.auth import ROLE_ADMIN, ROLE_READ, ROLE_WRITE
from core.redis_client import get_redis

RBAC_REDIS_KEY = "ninko:rbac:state"
PBKDF2_ITERATIONS = 210_000


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _normalize_module_id(module_id: str) -> str:
    return (module_id or "").strip().lower().replace("-", "_")


def _normalize_tenant_id(tenant_id: str) -> str:
    t = (tenant_id or "").strip().lower().replace(" ", "_")
    return t or "default"


def _default_roles() -> dict[str, dict[str, Any]]:
    return {
        "role_admin": {
            "id": "role_admin",
            "name": "Administrator",
            "description": "Vollzugriff auf alle Bereiche.",
            "base_role": ROLE_ADMIN,
            "module_permissions": {
                "*": {"read": True, "write": True},
            },
        },
        "role_operator": {
            "id": "role_operator",
            "name": "Operator",
            "description": "Schreibzugriff auf freigegebene Module.",
            "base_role": ROLE_WRITE,
            "module_permissions": {
                "*": {"read": True, "write": True},
            },
        },
        "role_viewer": {
            "id": "role_viewer",
            "name": "Viewer",
            "description": "Nur lesender Zugriff auf freigegebene Module.",
            "base_role": ROLE_READ,
            "module_permissions": {
                "*": {"read": True, "write": False},
            },
        },
    }


def _default_groups() -> dict[str, dict[str, Any]]:
    return {
        "group_admins": {
            "id": "group_admins",
            "name": "Admins",
            "description": "Administratoren-Gruppe.",
            "roles": ["role_admin"],
            "users": [],
        },
    }


def _default_state() -> dict[str, Any]:
    return {
        "version": 1,
        "users": {},
        "roles": _default_roles(),
        "groups": _default_groups(),
        "updated_at": _now_iso(),
    }


def hash_password(password: str, *, salt_b64: str | None = None) -> str:
    salt = base64.b64decode(salt_b64) if salt_b64 else os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return (
        f"pbkdf2_sha256${PBKDF2_ITERATIONS}$"
        f"{base64.b64encode(salt).decode('ascii')}$"
        f"{base64.b64encode(digest).decode('ascii')}"
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algo, iterations_raw, salt_b64, digest_b64 = encoded_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(digest_b64.encode("ascii"))
    except (ValueError, TypeError):
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(candidate, expected)


class RbacStore:
    async def load(self) -> dict[str, Any]:
        redis = get_redis()
        raw = await redis.connection.get(RBAC_REDIS_KEY)
        if not raw:
            state = _default_state()
            await self.save(state)
            return state

        data_raw = raw if isinstance(raw, str) else raw.decode("utf-8")
        state = json.loads(data_raw)
        if not isinstance(state, dict):
            state = _default_state()
        state.setdefault("users", {})
        state.setdefault("roles", _default_roles())
        state.setdefault("groups", _default_groups())
        state.setdefault("updated_at", _now_iso())
        return state

    async def save(self, state: dict[str, Any]) -> None:
        state["updated_at"] = _now_iso()
        redis = get_redis()
        await redis.connection.set(RBAC_REDIS_KEY, json.dumps(state))

    async def ensure_user(
        self,
        username: str,
        password: str,
        *,
        tenant_id: str = "default",
        roles: list[str] | None = None,
        groups: list[str] | None = None,
        active: bool = True,
    ) -> None:
        if not username.strip() or not password:
            return
        state = await self.load()
        users: dict[str, dict[str, Any]] = state["users"]
        uname = username.strip()
        user = users.get(uname)
        if user:
            return
        users[uname] = {
            "username": uname,
            "tenant_id": _normalize_tenant_id(tenant_id),
            "password_hash": hash_password(password),
            "active": active,
            "roles": roles or [],
            "groups": groups or [],
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        await self.save(state)

    async def bootstrap_admin_if_needed(self, username: str, password: str) -> None:
        if not username.strip() or not password:
            return
        state = await self.load()
        users: dict[str, dict[str, Any]] = state["users"]
        groups: dict[str, dict[str, Any]] = state["groups"]
        roles: dict[str, dict[str, Any]] = state["roles"]

        groups.setdefault("group_admins", _default_groups()["group_admins"])
        roles.setdefault("role_admin", _default_roles()["role_admin"])

        uname = username.strip()
        if uname not in users:
            users[uname] = {
                "username": uname,
                "tenant_id": "default",
                "password_hash": hash_password(password),
                "active": True,
                "roles": ["role_admin"],
                "groups": ["group_admins"],
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
            }
        else:
            user = users[uname]
            user["tenant_id"] = _normalize_tenant_id(str(user.get("tenant_id", "default")))
            role_ids = set(user.get("roles") or [])
            role_ids.add("role_admin")
            user["roles"] = sorted(role_ids)
            group_ids = set(user.get("groups") or [])
            group_ids.add("group_admins")
            user["groups"] = sorted(group_ids)
            user["updated_at"] = _now_iso()

        admin_group = groups["group_admins"]
        member_set = set(admin_group.get("users") or [])
        member_set.add(uname)
        admin_group["users"] = sorted(member_set)
        await self.save(state)

    async def authenticate_user(self, username: str, password: str) -> dict[str, Any] | None:
        state = await self.load()
        user = state["users"].get(username.strip())
        if not isinstance(user, dict):
            return None
        if not bool(user.get("active", True)):
            return None
        if not verify_password(password, str(user.get("password_hash", ""))):
            return None
        return user

    @staticmethod
    def _merge_base_role(current: str, candidate: str) -> str:
        order = {ROLE_READ: 1, ROLE_WRITE: 2, ROLE_ADMIN: 3}
        return candidate if order.get(candidate, 0) > order.get(current, 0) else current

    @staticmethod
    def _merge_module_permissions(
        target: dict[str, dict[str, bool]],
        source: dict[str, Any],
    ) -> None:
        for mod, perms in source.items():
            mod_id = _normalize_module_id(str(mod))
            if not mod_id:
                continue
            read = bool(isinstance(perms, dict) and perms.get("read", False))
            write = bool(isinstance(perms, dict) and perms.get("write", False))
            current = target.setdefault(mod_id, {"read": False, "write": False})
            current["read"] = current["read"] or read
            current["write"] = current["write"] or write

    async def build_effective_permissions(self, username: str) -> dict[str, Any] | None:
        state = await self.load()
        users: dict[str, dict[str, Any]] = state["users"]
        roles: dict[str, dict[str, Any]] = state["roles"]
        groups: dict[str, dict[str, Any]] = state["groups"]

        user = users.get(username.strip())
        if not isinstance(user, dict):
            return None

        role_ids = set(user.get("roles") or [])
        group_ids = set(user.get("groups") or [])
        for gid in list(group_ids):
            group = groups.get(gid)
            if isinstance(group, dict):
                role_ids.update(group.get("roles") or [])

        base_role = ROLE_READ
        module_permissions: dict[str, dict[str, bool]] = {}
        for rid in role_ids:
            role = roles.get(rid)
            if not isinstance(role, dict):
                continue
            base_role = self._merge_base_role(base_role, str(role.get("base_role", ROLE_READ)))
            self._merge_module_permissions(
                module_permissions,
                role.get("module_permissions") if isinstance(role.get("module_permissions"), dict) else {},
            )

        if not module_permissions:
            module_permissions["*"] = {
                "read": True,
                "write": base_role in {ROLE_WRITE, ROLE_ADMIN},
            }

        return {
            "username": username.strip(),
            "tenant_id": _normalize_tenant_id(str(user.get("tenant_id", "default"))),
            "base_role": base_role,
            "module_permissions": module_permissions,
            "role_ids": sorted(role_ids),
            "group_ids": sorted(group_ids),
        }
