#!/usr/bin/python

import sys

sys.path.insert(0, '/usr/lib/python2.7/bridge/')                                          
from bridgeclient import BridgeClient as bridgeclient

import json

json_config = open("/mnt/sda1/ac/conf/config.json");
config = json.load(json_config);
json_config.close();

zone = config["zone"];

json_users = open("/mnt/sda1/ac/conf/users.json");
users = json.load(json_users);
json_users.close();

bc = bridgeclient()

while True:
	code = bc.get("CODE")
	if (code):
		if (users.get(code) is None):
			bc.delete("CODE")
			continue
		if (users[code][zone] == "Yes"):
			bc.mailbox("O")
		bc.delete("CODE")

