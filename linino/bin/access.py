#!/usr/bin/python

import smtplib 
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

TO='access@ctrlh.org'
FROM= zone + '@ctrlh.org'
SUBJECT='Someone has entered ' + zone

def log(str):
	fd = open("/mnt/sda1/ac/log/logfile", 'w')
	fd.write(str + '\n')
	fd.close()
	
def send_email( str ):
	try:
		smtpserver = smtplib.SMTP("mail.ctrlh.org", 26)
		smtpserver.ehlo()
		header = 'To: ' + TO + '\nFrom: ' + FROM + '\nSubject: ' + SUBJECT + '\n'
		msg = header + '\n' + str + ' \n\n'
		smtpserver.sendmail(FROM, TO, msg)
		smtpserver.close()
	except smtplib.SMTPException:
		# couldn't send.
		log("Error connecting to SMTP server, continuing.")
		pass	
	
while True:
	code = bc.get("CODE")
	if (code):
		if (users.get(code) is None):
			bc.delete("CODE")
			continue
		if (users[code][zone] == "Yes"):
			bc.mailbox("O")
			name = users[code].get("Name")
			log("Allowed user " + name)
			send_email(name)
		bc.delete("CODE")
