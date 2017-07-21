"""Better version of config.

Things I don't like about config:
 - Per class, so can't have multiple bots in same process.
 - There's a race condition between cog instantiation and config setting, which
    affects basically everything I care about.
 - It's not injectable, so there's too much magic going on, makes testing
    awkward.


Potential usage example:


@docg()
class SomeCog:
    api_key = ConfigEntry()

    def __init__(self, config):
        self._config = config
        self.api = Api(key=self.api_key)


api_key does a lookup self._config['api_key']

config is a group, node, or something.

Maybe I could add a metaclass that handles all the injection __init__ stuff for
me lol.

class SomeCog(metaclass=CogMeta):
    database = Depends("Database")
    redis = Depends("Redis")
    api_key = Config()  # defaults to name of variable
    max_connections = Config(default=4)

Then CogMeta looks at members, and then creates an __init__ that takes those
arguments.



Could go for no-magic mode:

@dcog()
class SomeCog:
    def __init__(self, config):
        self.api_key = config.register("api_key")
        self.max_connections = config.register("max_conn", default=4)

No magic-mode seems to make sense.


On configuration side, we'll have:
 - FileConfiguration : a config tied to a filename
 - StringConfiguration : a config tied to string
 - ConfigGroup : group tied to a configuration
   - Special group FileConfiguration.root has no prefix, parses root tree
   - A group has members, which can be a group, or a value
   - ConfigGroup.register() returns a ConfigValue, a descriptor tied to a
     config.
   - ConfigGroup.add_group() returns a ConfigGroup, tied to the group/config


"""
import io
import ruamel.yaml


class InvalidConfig(Exception):
    pass


class ConfigEntry:
    """Descriptor tied to a config."""

    def __init__(self, config, default=None, validator=None, path=None):
        self._config = config
        self._path = path
        self.default = default

    @property
    def value(self):
        return self._config.get(self._path)

    def __call__(self):
        return self.value


class ConfigGroup:
    def __init__(self, config, path=None):
        self._config = config
        self._path = path or []
        self._entries = {}

    def register(self, value_name, default=None, validator=None):
        """Register config entry.

        Raises if loaded configuration is invalid.
        """
        entry = ConfigEntry(
            self._config, default, validator, path=self._path + [value_name])
        self._entries[value_name] = entry
        if not self.validate():
            raise InvalidConfig
        return entry

    def add_group(self, group_name):
        group = ConfigGroup(self._config, self._path + [group_name])
        self._entries[group_name] = group
        self.validate()
        return group

    def remove_group(self, group_name):
        del self._entries[group_name]
        self.validate()

    def validate(self):
        """Raise if configuration is not valid.

        If entry is not present, the default value is set.
        If we changed configuration data, comment set where we changed it.
        """
        data = self._config.get(self._path)
        valid = True

        for key, entry in self._entries.items():
            if key not in data or data[key] is None:
                if isinstance(entry, ConfigGroup):
                    data[key] = self._config._yaml.map()
                elif entry.default is not None:
                    data[key] = entry.default
                    data.yaml_add_eol_comment("Default value", key)
                else:
                    data[key] = None
                    data.yaml_add_eol_comment("Required value", key)
                    valid = False
        return valid


class Configuration:
    def __init__(self):
        self._yaml = ruamel.yaml.YAML()
        self.root = ConfigGroup(self)

    def get(self, path):
        cur = self._data
        while path:
            cur = cur[path[0]]
            path = path[1:]
        return cur

    def dumps(self):
        buff = io.StringIO()
        data = self._data.copy()
        for key, val in self._data.items():
            if val == {}:
                del data[key]

        self._yaml.dump(data, buff)
        buff.seek(0)
        return buff.read()


class StringConfiguration(Configuration):
    def __init__(self, string):
        super().__init__()
        self._data = self._yaml.load(string) or self._yaml.map()


class FileConfiguration(Configuration):
    def __init__(self, filename):
        super().__init__()
        self._filename = filename

    def load(self):
        try:
            with open(self._filename) as f:
                self._data = self._yaml.load(f.read())
        except FileNotFoundError:
            self._data = self._yaml.map()

    def save(self):
        with open(self._filename, 'w') as f:
            data = self._data.copy()
            for key, val in self._data.items():
                if isinstance(val, dict) and not val:
                    del data[key]
            self._yaml.dump(data, f)
