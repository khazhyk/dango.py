"""Grants permissioning system.

Default permission nodes:

Commands have implicit permission nodes, corresponding to the
cog and command name. (For commands without a cog, the cog name is "bot")

The special implicit command nodes are all granted by default (equivilent to default_allow([whatever]))
This allows denying specific commands to specific users/etc. Or restricting some commands more than before.
(This also allows "disabling" a command server wide, but isn't the intended purpose). But like, if you
want to only allow mods to use the userinfo command, you can default_deny("info.userinfo"),
then role_allow("info.userinfo", "mods")



grants.check() allows specifying an additional node required. To use the command, you
would need *both* the additional node, and the command node. This is to allow cogs to specify
logical permissioning groups.

grants.require() allows specifing an additional node required within the execution of a command,
usually on a conditional basis. E.g.: you can edit your own tags, but need extra permission to edit
others'

To avoid footguns, the explicit nodes specified by grants.check() and grants.require are *not* granted
to default, and if that is desired, do that in the permission default stuff. *Warn if you try and
specify an implict node in these explicit checks* ("cog.perm is the same as the command cog.perm,
choose a different name for this permission")

Node based permissions, stuff like "tag.create, tag.edit, tag.edit.others, tag.delete.others"

@command()
@grants.check("cog.my_perm")  # returns a "check" for the normal d.py check
async def my_command(self, ctx):
    if exceptional_circumstance:
        grants.require("cog.my_perm.override", ctx)  # Check ctx author has the grant

And granting systems:
e.g.: grant tag.create to all, grant tag.delete.others to users with manage messages.
*nodes required* are specified at the command level. *default grants* are specified at the cog
level, just so there's no confusion if, e.g., a command has default_deny, but a server allows it?

All permissions are, by default, denied, except for implicit permissions
This can be overridden, in order, by:
 - guild grants (everyone)
 - discord guild permission grants
 - discord role grants
 - discord user grants

With an explicit allow/deny at the most specific level overriding anything above.

Also specify the default configuration for the permissions

async def __init__(self):
    # Allow creating, editing, and deleting own tags by default
    # Prefer to use the grants.check()
    grants.global_allow(["tag.create", "tag.edit", "tag.delete"])
    # Allow users with manage_messages to delete others' tags
    grants.permission_allow("manage_messages", ["tag.delete.other"])
    # Allow a special role named admin to edit and delete tags
    grants.role_allow("spoo.py admin", ["tag.edit.other", "tag.delete.other"])
    # Disallow abusive user from accessing tags
    grants.user_deny(123456789, ["tag.*"])

cogs should generally start the permission node with the cog name, and should not grant or
check for other cogs' permissions.

Eventually meant to allow user configuration of this stuff, with cogs allowing specifying default
configs which can be changed per server. For simplicities sake, permissions can *only* be configured,
not per channel.

# All implicit nodes are allowed to default ("cog.command_name")
# All explicit nodes are denied to default ("cog.special_perm")
# If a user is allowed and denied on the same level (e.g., in a role that allows,
#   and another role that denies), it will deny
{
    grants: {
        guild_deny: ["info.userinfo"],  # Override userinfo default
        role_allow: {"my_mode_role": ["info.userinfo"]}  # Grant it to mods
        role_deny: {"no_memes": ["fun.*"]}  # remove access to the fun cog for no_memes users
    }
}

# Need to have some way to show the full, resolved permission config

{
    grants: {
        default: ["tag.create", "tag.edit", "tag.remove", "tag.info"],
        default_deny: ["tag.edit.others", "tag.remove.others"],
        permission_allow: {"manage_messages": ["tag.edit.others", "tag.remove.others"]}
    }
}

Storing permissions:
 * Only store *deltas* from default into database. This will shrink the required storage significantly
Resolving new nodes with existing configuration:
 * For default, take the explicit defaults, then merge the rest for anything not explicitly mentioned
 * Each node most be present exactly once in defaults, either allow or deny.
 * To "reset" a by-default permission/group grant, store "reset"
 * If reset isn't specified for that specific permission-grant pair, use the cog default.
 
So for example, if we have some commands that are default restricted to manage_messages, but a server
wants to instead restrict it only to a group, the configuration in-database would look like:

{
    grants: {
        permission_reset: {"manage_messages": ["tag.edit.others", "tag.remove.others"]}
        role_allow: {"my mod role": ["tag.edit.others", "tag.remove.others"]}
    }
}

and the full resolved permissions would look like:
{
    grants: {
        default_guild_allow: [...]
        default_guild_deny: [...]
        guild_allow: [overrides...]
        guild_deny: [overrides...]
        default_permission_allow: {}
        permission_reset: {} # this is used to clear default_permission_allow
        permission_allow: # now we can specify our own permission_allow, without worrying about conflicts from defaults!
    }
}

eh, it should be clear to the end-user which fields are "defaults" and which fields they should specify.
(e.g., i wouldn't want someone copy-pasting the full resolved stuff into the config, resulting in bloat, and
not getting any changes to defaults)


Example:

tags!

tag (access to command at all, show tag)
tag.manage (create, edit, delete own tags)
tag.manage_others (edit, delete other tags)

# Since it's an explicit node, we specify we want everyone to have it
grants.guild_allow(["tags.manage"])
grants.permission_allow(manage_messages=["tag.manage_others"])


So for a guild that wants to, e.g., disallow creating tags, but allow mods to do it, they'd 
specify a config:
{
    grants: {
        guild_deny: "tag.manage"  # At default level, *only* allow or deny
        permission_reset: {"manage_messages": ["tag.manage_others"]}  # This must match to a default permission!
        role_allow: {
            "my_mod_role": ["tag.manage"]  # Allow mods to create/edit tags
            "my_admin_role": ["tag.manage", "tag.manage_others"]  # Allow admins to create/edit tags, and manage others'
        } 
    }
}

Then, looking at *resolved* config:
{
    resolved_grants: {
        guild_allow: ["tag.tag", "tag.tag.create", "tag.tag.edit", "tag.tag.remove"],
        guild_deny: ["tag.manage", "tag.manage_others"],
        role_allow: {
            "my_mod_role": ["tag.manage"],
            "my_admin_role": ["tag.manage", "tag.manage_others"]
        }
    }
}

And looking at the full layered config:
{
    grants: {
        default_guild_allow: ["tag.tag", "tag.tag.create", "tag.tag.edit", "tag.tag.remove", "tag.manage"],
        default_guild_deny: ["tag.manage_others"]
        guild_deny: ["tag.manage"]
        default_permission_allow: {"manage_messages": ["tag.manage_others"]}
        permission_reset: {"manage_messages": ["tag.manage_others"]}
        role_allow: {
            "my_mod_role": ["tag.manage"],
            "my_admin_role": ["tag.manage", "tag.manage_others"]
        }
    }
}




side note: idea
?guild command to allow running commands from DM but in a guild-context
allow people to quietly edit config, etc.? maybe??? but also grab userinfo etc.? idk, maybe too sneaky


also: for the purposes of this, these grants are *all grantable by the server owner*!!!
so ***NOT FOR OWNER-ONLY/DEBUG COMMANDS***
do NOT!!!!


OK then, how to actually implement this?

For the config portion, we need to rely on a database config which provides the override JSON. (TODO)

Then per-cog we need to have a default JSON.
Also per-cog, we need to know the name of all commands and subcommands
For the "resolved config", we need to know all explicit permission nodes.

The full resolved config will:
 - be per guild
 - have info for *all* cogs
 - be kinda big...


On grant check:
 - lookup database, if needed
 - For guild grants, apply the implicit, explicit defaults, if not present in override
 - For other grants, if reset isn't present, apply it.

Then:
 * check if user grant exists for user
 * check if role grant exists for user
 * check if permission grant exists for user
 * use guild grant

When operating in DM-context, all grants are assumed to be had!


# Cog loading and unloading
- just clear all all cached resolved grants! e.z.


All global metadata will be stored on the cog.
Anyone importing this file directly will have an implicit reload due to
this folder being a cog, even without directly depending on the cog...

So the question is:
how will the decorators work lmao?

I think:
decorator just assumes that ~there exists a cog named Grants~,
which is instanceof Grants,
so we find that, and run the check!
So we have to do get_cog each time.?
IDK mang, that's weird. How about this:

grants has a global check. (duh, it's needed anyways for the defaults)
the decorators add a special __dango_grants property, which the global
check checks for.

yeah, solid!

"""