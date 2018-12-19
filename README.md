# Netdisco Ansible inventory 
## Description
Enables the use of Netdisco, or any PSQL DB, as a source for ansible dynamic inventory.

## Installation
prereqs:
* Ansible already installed
* Netdisco (or whatever PSQL DB) running and with pg_hba.conf configured, and a user added.
    

```bash
# Configure your ansible details first!
export ANSIBLE_ROOT_DIR=/path/to/ansible
# Example: export ANSIBLE_ROOT_DIR=/etc/ansible

# Install deps
pip install psycopg2
pip install PyYaml
pip install jinja2

# Clone this repo
git clone https://github.com/adambaumeister/netdisco_ansible_inventory.git

# Copy files to their places
mkdir $ANSIBLE_ROOT_DIR/inventory
cp netdisco_ansible_inventory/inv.yml $ANSIBLE_ROOT_DIR/inv.yml
cp netdisco_ansible_inventory/nd_inv.py $ANSIBLE_ROOT_DIR/inventory/nd_inv.py

### DON'T MISS THIS STEP ###
# Configure the inventory script for your environment!
vi $ANSIBLE_ROOT_DIR/inv.yml
```

Post install and configuration, you can test by running the script directly.

--list is the option Ansible passes to dynamic inventory scripts by default.

```bash
cd $ANSIBLE_ROOT_DIR/inventory
python nd_inv.py --list
```

## Usage
nd_inv.py, by virtue of being in the Inventory directory, will run whenever ansible is run.

It parses the inv.yml config file looking for Inputs. Inputs must be configured with a query and other DB specific stuff, see the example inv.yml file in this repo.

The script queries the database using select_query, then parses the resultant rows of the query and converts them into Ansible groups.

This allows you to reference the groups, or individual hosts, as normal in playbooks such as:
```yaml
- hosts: test-36xxstack
```

or 

```yaml
- hosts: my-switch-from-netdisco.org.com
```
