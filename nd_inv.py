#!/usr/bin/env python
import psycopg2
import psycopg2.extras
import yaml
import re
from jinja2 import Template
import json
import argparse
import sys
import os

class ScriptConfiguration:
    def __init__(self, filename):
        self.inputs = {}
        self.outputs = {}
        self.type_sw = {
            'psql': psql,
            'AnsibleJSON': AnsibleJSON,
            'AnsibleINI': AnsibleINI,
        }
        yaml_file = open(filename, 'r')
        try:
            yaml_obj = yaml.load(yaml_file)
        except yaml.YAMLError as err:
            print(err)
            exit()

        # Validate
        if 'Input' not in yaml_obj:
            raise ValueError("Invalid YAML format - missing data")
        if 'Output' not in yaml_obj:
            raise ValueError("Invalid YAML format - missing data")

        # Load inputs
        for name, attrs in yaml_obj['Input'].items():
            t = attrs['type']
            if "use" in attrs:
                i = self.type_sw[t](attrs, use=yaml_obj['Input'][attrs["use"]])
            else:
                i = self.type_sw[t](attrs)

            self.inputs[name] = i

        for name, attrs in yaml_obj['Output'].items():
            t = attrs['type']
            i = self.type_sw[t](attrs)
            self.outputs[name] = i

    # Only honor the passed input
    def filter_outputs(self, output):
        self.outputs = {
            output: self.outputs[output]
        }

    def generate(self):
        # Init inputs
        for name, i in self.inputs.items():
            data = i.get()
            data = i.transform(data)
            grouped = i.group(data)
            for name, o in self.outputs.items():
                if "host_vars" in i.config:
                    host_vars = i.vars(data)
                    o.add_host_vars(host_vars)
                o.add_grouped_data(grouped)

        # Write outputs
        for name, o in self.outputs.items():
            o.out()

# Base class for Output types
class Output(object):
    def __init__(self, config):
        struct = [
            'type'
        ]
        self.transforms = []
        for k in struct:
            if k not in config:
                raise ValueError("Invalid YAML - missing {0} in struct".format(k))
        self.config = config

    def get(self):
        return

    def out(self):
        if "file" in self.config:
            f = open(self.config["file"], "w")
            f.write(self.get())
        else:
            print(self.get())

# Ansible formatted JSON output method
class AnsibleJSON(Output):
    def __init__(self, config):
        super(AnsibleJSON, self).__init__(config)
        self.formatted = {}
        self.hostvars = {}

    # Add grouped data
    def add_grouped_data(self, grouped):
        for group, hosts in grouped.items():
            struct = {
                'hosts': hosts,
            }
            self.formatted[group] = struct

    def add_host_vars(self, vars):
        self.hostvars = vars

    def dump(self):
        # Required to prevent --host being called for every host
        print(json.dumps(self.formatted, indent=4, sort_keys=True, separators=(',', ': ')))

    def prints(self):
        self.formatted['_meta'] = {
            'hostvars': self.hostvars
        }
        print(json.dumps(self.formatted))

    def get(self):
        self.formatted['_meta'] = {
            'hostvars': self.hostvars
        }
        return json.dumps(self.formatted)

class AnsibleINI(Output):
    """
    AnsibleINI Format 
    Example:
    [ group ]
    host1
    host2 
    """
    def __init__(self, config):
        super(AnsibleINI, self).__init__(config)
        self.formatted = {}
        self.hostvars = {}

    # Add grouped data
    def add_grouped_data(self, grouped):
        hosts_with_vars = []
        for group, hosts in grouped.items():
            for host in hosts:
                if host in self.hostvars:
                    str = self.vars_to_string(self.hostvars[host])
                    str = "{} {}".format(host, str)
                    hosts_with_vars.append(str)
                else:
                    hosts_with_vars.append(host)

            l = "\n".join(hosts_with_vars)
            self.formatted[group] = l

    def vars_to_string(self, vars):
        pairs = []
        for k, v in vars.items():
            s = "{}={}".format(k, v)
            pairs.append(s)

        return " ".join(pairs)
    
    def dump(self):
        lines =[] 
        for group, hosts in self.formatted.items():
            lines.append("[{0}]".format(group))
            lines.append("{0}".format(hosts))
            # Newline
            lines.append("")
        return lines

    def add_host_vars(self, vars):
        self.hostvars = vars

    def prints(self):
        for line in self.dump():
            print(line)

    def get(self):
        s = ''
        for line in self.dump():
            s = s + line + "\n"
        return s


# Base Class for Inputs
class Input(object):
    def __init__(self, config, use=None):
        """
        Base Input class
        :param config: Dictionary of configuration for this input type
        :param use: Dictionary of configuration to inherit
        """
        struct = [
            'group_field',
            'host_field'
        ]

        self.transforms = []

        self.config = config
        if use:
            self.use(use)

        for k in struct:
            if k not in config:
                raise ValueError("Invalid YAML - missing {0} in struct".format(k))

        if 'transform' in self.config:
            for transform in self.config['transform']:
                t = Transform(transform)
                self.transforms.append(t)

    def use(self, config):
        """
        If a "use" statement is configured, inherit settings that aren't configured from it
        :var config (DICT): Dictionary of configuration for this input
        :return: None
        """
        for k, v in config.items():
            if k not in self.config:
                self.config[k] = v


    def transform(self, data):
        newdata = data
        for t in self.transforms:
            newdata = t.do(newdata)
        return newdata

    def group(self, data):
        grouped = data.group(self.config['group_field'], self.config['host_field'])
        return grouped

    def vars(self, data):
        vars = {}
        for row in data.get_rows():
            v = {}
            for var_def in self.config['host_vars']:
                col = var_def['column']
                vard = var_def['var']
                if col in row:
                    v[vard] = row[col]
            vars[row[self.config['host_field']]] = v

        return vars
# Postgres Input method
class psql(Input):
    def __init__(self, config, use=None):
        super(psql, self).__init__(config, use)
        self.dsn = "dbname='{0}' user='{1}' host='{2}' password='{3}'".format(
            self.config['dbname'], self.config['user'], self.config['host'], self.config['password']
        )
        self.query = self.config['select']

    def get(self):
        conn = psycopg2.connect(self.dsn)
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(self.query)
        data = Data()

        for row in cur:
            # simplify the sql data
            s = {}
            for k, v in row.items():
                s[k] = v
            data.add_row(s)

        return data

# Transform class, transforms data within a dict
class Transform:
    def __init__(self, config):
        struct = [
            'field',
            'regex',
            'out',
        ]
        for k in struct:
            if k not in config:
                raise ValueError("Invalid YAML - missing {0} in struct".format(k))
        self.field = config['field']
        self.regex = config['regex']
        self.out = config['out']

    def do(self, data):
        newdata = Data()
        for row in data.get_rows():
            newrow = row
            if self.field not in row:
                raise ValueError("Invalid data in transform - field {0} does not exist".format(self.field))

            v = re.match(self.regex, row[self.field])
            # Note: transform filters the data such that if the regex does not match, that row is omitted
            if v:
                v = v.group(1)
                newrow[self.out] = v
                newdata.add_row(newrow)
        return newdata


# Data represents the underlying input
# It is comprised of a list of dictionaries
class Data:
    def __init__(self):
        self.rows = []
        # Host variarbles 
        self.vars = {}

    def add_row(self, dict):
        self.rows.append(dict)

    def get_rows(self):
        return self.rows

    def group(self, group_field, host_field):
        grouped = {}
        for row in self.get_rows():
            group = self.sub_variables(row, group_field)
            host = row[host_field]
            if group not in grouped:
                grouped[group] = []
            grouped[group].append(host)
        return grouped

    def sub_variables(self, row, string):
        template = Template(string)
        result = template.render(row)
        return result

# Parse commandline arguments
parser = argparse.ArgumentParser()
parser.add_argument('--list', action="store_true", dest="list", help="List output")
parser.add_argument('--host', action="store_true", dest="host", help="Host vars")
parser.add_argument('--output', action="store", dest="output", help="Only run a specific output.")

args = parser.parse_args()
# Dump json
rundir = sys.path[0]
# Config file is one directory back usually, in the root of the ansible directory
scf = os.path.join(rundir, "..", "inv.yml")
# If it isn't then we use the current directory.
if not os.path.exists(scf):
    scf = os.path.join("inv.yml")
if args.list:
    c = ScriptConfiguration(scf)
    c.generate()
elif args.output:
    c = ScriptConfiguration(scf)
    c.filter_outputs(args.output)
    c.generate()

# dump nothing
elif args.host:
    print({})
else:
    raise ValueError("Missing arguments!")