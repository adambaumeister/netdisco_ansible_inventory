# Netdisco Ansible inventory 
## Description
Enables the use of Netdisco, or any PSQL DB, as a source for ansible dynamic inventory.

## Installation
First, install the dependencies via Pip
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