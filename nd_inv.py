#!/usr/bin/env python
import psycopg2
import psycopg2.extras
import yaml
import re
from jinja2 import Template
import json
import argparse
import sys

class ScriptConfiguration:
    def __init__(self, filename):
        self.inputs = {}
        self.outputs = {}
        self.type_sw = {
            'psql': psql,
            'AnsibleJSON': AnsibleJSON,
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
            i = self.type_sw[t](attrs)
            self.inputs[name] = i

        for name, attrs in yaml_obj['Output'].items():
            t = attrs['type']
            i = self.type_sw[t](attrs)
            self.outputs[name] = i

    def generate(self):
        # Init inputs
        for name, i in self.inputs.items():
            data = i.get()
            data = i.transform(data)
            grouped = i.group(data)
            for name, o in self.outputs.items():
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


# Ansible formatted JSON output method
class AnsibleJSON(Output):
    def __init__(self, config):
        super(AnsibleJSON, self).__init__(config)
        self.formatted = {}

    # Add grouped data
    def add_grouped_data(self, grouped):
        for group, hosts in grouped.items():
            struct = {
                'hosts': hosts,
            }
            self.formatted[group] = struct

    def dump(self):
        # Required to prevent --host being called for every host
        print(json.dumps(self.formatted, indent=4, sort_keys=True, separators=(',', ': ')))

    def out(self):
        self.formatted['_meta'] = {
            'hostvars': {}
        }
        print(json.dumps(self.formatted))


# Base Class for Inputs
class Input(object):
    def __init__(self, config):
        struct = [
            'group_field',
            'host_field'
        ]
        self.transforms = []
        for k in struct:
            if k not in config:
                raise ValueError("Invalid YAML - missing {0} in struct".format(k))
        self.config = config

        if 'transform' in self.config:
            for transform in self.config['transform']:
                t = Transform(transform)
                self.transforms.append(t)

    def transform(self, data):
        newdata = data
        for t in self.transforms:
            newdata = t.do(newdata)
        return newdata

    def group(self, data):
        grouped = data.group(self.config['group_field'], self.config['host_field'])
        return grouped

# Postgres Input method
class psql(Input):
    def __init__(self, config):
        super(psql, self).__init__(config)
        self.dsn = "dbname='{0}' user='{1}' host='{2}' password='{3}'".format(
            config['dbname'], config['user'], config['host'], config['password']
        )
        self.query = config['select']

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

args = parser.parse_args()
# Dump json
rundir = sys.path[0]
if args.list:
    c = ScriptConfiguration('{0}/../inv.yml'.format(rundir))
    c.generate()
# dump nothing
elif args.host:
    print({})
else:
    raise ValueError("Missing arguments!")