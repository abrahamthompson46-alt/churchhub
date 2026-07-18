"""Role definitions for ChurchHub RBAC."""

from permissions.registry import registry_default_roles


class UserRole:
    """Application roles — stored as strings on User.role."""

    SUPER_ADMIN = "SUPER_ADMIN"
    GENERAL_OVERSEER = "GENERAL_OVERSEER"
    UNION_ADMIN = "UNION_ADMIN"
    CONFERENCE_ADMIN = "CONFERENCE_ADMIN"
    ZONE_DIRECTOR = "ZONE_DIRECTOR"
    DISTRICT_PASTOR = "DISTRICT_PASTOR"
    LOCAL_PASTOR = "LOCAL_PASTOR"
    SECRETARY = "SECRETARY"
    TREASURY = "TREASURY"
    BOARD_MEMBER = "BOARD_MEMBER"
    MEMBER = "MEMBER"

    CHOICES = [
        (SUPER_ADMIN, "Super Admin"),
        (GENERAL_OVERSEER, "General Overseer"),
        (UNION_ADMIN, "Union Administrator"),
        (CONFERENCE_ADMIN, "Conference Administrator"),
        (ZONE_DIRECTOR, "Zone Director"),
        (DISTRICT_PASTOR, "District Administrator"),
        (LOCAL_PASTOR, "Local Pastor"),
        (SECRETARY, "Secretary"),
        (TREASURY, "Treasury"),
        (BOARD_MEMBER, "Board Member"),
        (MEMBER, "Member"),
    ]

    HIERARCHY = [
        SUPER_ADMIN,
        GENERAL_OVERSEER,
        UNION_ADMIN,
        CONFERENCE_ADMIN,
        ZONE_DIRECTOR,
        DISTRICT_PASTOR,
        LOCAL_PASTOR,
        SECRETARY,
        TREASURY,
        BOARD_MEMBER,
        MEMBER,
    ]

    # Org-tree administrators (subtree managers)
    TREE_ADMIN_ROLES = {
        SUPER_ADMIN,
        GENERAL_OVERSEER,
        UNION_ADMIN,
        CONFERENCE_ADMIN,
        ZONE_DIRECTOR,
        DISTRICT_PASTOR,
    }

    ASSIGNABLE_BY_ROLE = {
        SUPER_ADMIN: (
            GENERAL_OVERSEER,
            UNION_ADMIN,
            CONFERENCE_ADMIN,
            ZONE_DIRECTOR,
            DISTRICT_PASTOR,
            LOCAL_PASTOR,
            SECRETARY,
            TREASURY,
            BOARD_MEMBER,
            MEMBER,
        ),
        GENERAL_OVERSEER: (
            UNION_ADMIN,
            CONFERENCE_ADMIN,
            ZONE_DIRECTOR,
            DISTRICT_PASTOR,
            LOCAL_PASTOR,
            SECRETARY,
            TREASURY,
            BOARD_MEMBER,
            MEMBER,
        ),
        UNION_ADMIN: (
            CONFERENCE_ADMIN,
            ZONE_DIRECTOR,
            DISTRICT_PASTOR,
            LOCAL_PASTOR,
            SECRETARY,
            TREASURY,
            BOARD_MEMBER,
            MEMBER,
        ),
        CONFERENCE_ADMIN: (
            ZONE_DIRECTOR,
            DISTRICT_PASTOR,
            LOCAL_PASTOR,
            SECRETARY,
            TREASURY,
            BOARD_MEMBER,
            MEMBER,
        ),
        ZONE_DIRECTOR: (
            DISTRICT_PASTOR,
            LOCAL_PASTOR,
            SECRETARY,
            TREASURY,
            BOARD_MEMBER,
            MEMBER,
        ),
        DISTRICT_PASTOR: (
            LOCAL_PASTOR,
            SECRETARY,
            TREASURY,
            BOARD_MEMBER,
            MEMBER,
        ),
        LOCAL_PASTOR: (
            SECRETARY,
            TREASURY,
            BOARD_MEMBER,
            MEMBER,
        ),
        SECRETARY: (MEMBER,),
        TREASURY: (MEMBER,),
        BOARD_MEMBER: (MEMBER,),
        MEMBER: (),
    }

    @classmethod
    def label(cls, role):
        return dict(cls.CHOICES).get(role, role)

    @classmethod
    def requires_church(cls, role):
        """Local operational roles must have a home church."""
        return role not in cls.TREE_ADMIN_ROLES

    @classmethod
    def is_tree_admin(cls, role):
        return role in cls.TREE_ADMIN_ROLES

    @classmethod
    def rank(cls, role):
        try:
            return cls.HIERARCHY.index(role)
        except ValueError:
            return len(cls.HIERARCHY)

    @classmethod
    def can_assign_role(cls, actor_role, target_role, *, actor_is_superuser=False):
        """Actor may assign target only if listed in ASSIGNABLE_BY_ROLE (or superuser)."""
        if actor_is_superuser:
            return True
        if actor_role == cls.SUPER_ADMIN:
            return target_role != cls.SUPER_ADMIN
        allowed = cls.ASSIGNABLE_BY_ROLE.get(actor_role, ())
        return target_role in allowed

    @classmethod
    def assignable_role_choices(cls, actor):
        """Return CHOICES filtered for what *actor* may assign."""
        if getattr(actor, "is_superuser", False):
            return list(cls.CHOICES)
        actor_role = getattr(actor, "role", None)
        if actor_role == cls.SUPER_ADMIN:
            return [c for c in cls.CHOICES if c[0] != cls.SUPER_ADMIN]
        allowed = set(cls.ASSIGNABLE_BY_ROLE.get(actor_role, ()))
        return [c for c in cls.CHOICES if c[0] in allowed]


# Legacy role-set aliases — derived from registry defaults for backward compatibility.
FINANCIAL_ROLES = registry_default_roles("manage_finances")
APPROVAL_ROLES = registry_default_roles("approve_transactions")
HIERARCHY_ROLES = registry_default_roles("view_all_churches")
MEMBER_MANAGEMENT_ROLES = registry_default_roles("manage_members") | registry_default_roles("view_members")
USER_MANAGEMENT_ROLES = registry_default_roles("manage_users")
APPROVE_ANNOUNCEMENT_ROLES = registry_default_roles("approve_announcements")
PERMISSION_ADMIN_ROLES = registry_default_roles("manage_permissions")

ROLE_GROUP_MAP = {}
