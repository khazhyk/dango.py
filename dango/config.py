"""YAML based bot configuration.

Allows plugins to declare namespaced configuration options, populated defaults,
refuse to load until proper configuration is provided.
"""
import inspect
import re
import ruamel.yaml


def snakify(name):
    """Turn CamelCase into snake_case."""
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


class ConfigDesc:
    """Config description."""


class ConfigEntry(ConfigDesc):
    """Defines a config entry.

    Args:
        name : The name of the argument as shown in the configuration file
        arg_type : Type to parse this argument as.
        default : (Optional) The default to persist to the configuration if not
            set. If not set, and configuration does not provide the entry, the
            cog will refuse to load.
    """

    def __init__(self, name, default=None, group=None):
        self.name = name
        self.default = default
        self.group = group
        self._value = default

    @property
    def value(self):
        return self._value

    def load(self, value):
        self._value = value


class ConfigGroup(ConfigDesc):
    """Defines a config group.

    Args:
        name : Name of this group.
    """

    def __init__(self, name, group=None):
        self.name = name
        self.group = group
        self.entries = {}

    def add_entry(self, entry):
        self.entries[entry.name] = entry

    def entry(self, *args, **kwargs):
        e = ConfigEntry(*args, **kwargs, group=self)
        self.entries[e.name] = e
        return e

    def load(self, data):
        for key, value in data.items():
            self.entries[key].load(value)
        # Add items for unused entries


class Configuration:
    """YAML based per-cog configuration."""

    def __init__(self, filename=None, fp=None):
        self.filename = filename
        self.yaml = ruamel.yaml.YAML()
        self.root = ConfigGroup("root")

    def add_entry(self, entry):
        entry.group = self.root
        self.root.add_entry(entry)

    def add(self, thing):
        for field, member in inspect.getmembers(thing):
            if isinstance(member, ConfigDesc) and member.group is None:
                self.root.add_entry(member)

    def add_cog(self, cog):
        cog_cgroup = ConfigGroup(snakify(cog.__class__.__name__))
        for field, member in inspect.getmembers(cog):
            if isinstance(member, ConfigDesc) and member.group is None:
                cog_cgroup.add_entry(member)
        self.add_entry(cog_cgroup)

    def remove_cog(self, cog):
        try:
            del self.root.entries[snakify(cog.__class__.__name__)]
        except KeyError:
            pass

    def load(self):
        with open(self.filename) as f:
            data = f.read()

        self.load_str(data)

    def load_str(self, stri):
        for key, value in self.yaml.load(stri).items():
            try:
                self.root.entries[key].load(value)
            except KeyError:
                pass

    def save(self):
        pass

    def populate_missing_thing(self, data):
        data["item"] = None
        data.yaml_add_eol_comment("This element is required", "item")
