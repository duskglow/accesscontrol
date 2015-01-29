#!/usr/bin/python
#import daemon	# This is not used anymore
import RPi.GPIO as GPIO
import sys,time
import subprocess

import json
import smtplib

conf_dir = './conf/'

json_zone = open(conf_dir + 'zone.json');
jzone = json.load(json_zone);
json_zone.close();

zone = jzone["zone"];

json_users = open(conf_dir + 'users.json');
users = json.load(json_users);
json_users.close();

json_config = open(conf_dir + 'config.json');
config = json.load(json_config);
json_config.close();

json_locker = open(conf_dir + 'locker.json');
locker = json.load(json_locker);
json_locker.close();

if (zone == "locker"):
	lockerzone = jzone["lockerzone"]

# initialize some variables, should do this in a def.
active = config[zone]["Active"]
if (active != "High" and active != "Low"):
	print ("Invalid active directive for zone " + zone)
	sys.exit(0)

GPIO.setmode(GPIO.BCM)

def initGPIO():
	if (zone == "locker"):
		for relay in iter(locker):
			r = int(locker[relay]["Relay"])
			GPIO.setup(r, GPIO.OUT)
			GPIO.output(r, True)
	else :
		r = int(config[zone]["Relay"])
		GPIO.setup(r, GPIO.OUT)
		GPIO.output(r, False)
		
	
def triggerRelay(r, open_hours=False):
	relay = int(r)
	if (zone == "locker"):
		GPIO.output(relay, False)
		time.sleep(2)
		GPIO.output(relay, True)
	else:
		GPIO.output(relay, True)
		if (open_hours):
			return True
		time.sleep(0.1)
		GPIO.output(relay, False)

def decodeStr( line ):
	tbstr = line.split(" : ")[1]
	tbstr = tbstr.rstrip()
	bstr = tbstr[0:24] + tbstr[30:]

	if len(bstr) != 26:
		#print("Incorrect string length received: " + str(len(bstr)))
		#print(":" + bstr + ":")
		return -1
	lparity = bstr[0]
	facility = bstr[1:9]
	id = bstr[9:25]
	rparity = bstr[25]
	lpstr = bstr[1:13]
	rpstr = bstr[13:25]

	#print(line)
	#print(lparity + " " + facility + " " + id + " " + rparity)
	# check parity
	pcnt = 0
	for iter in range(0, 12):
		if (lpstr[iter] == "1"):
			pcnt += 1
	if (pcnt % 2 == lparity):
		#print("Left parity Error in received string!")
		return -1

	pcnt = 0
	for iter in range(0, 12):
		if (rpstr[iter] == "1"):
			pcnt += 1
	if (pcnt % 2 == rparity):
		#print("Right parity Error in received string!")
		return -1

	return int(id, 2)

def send_email( subject, body ):
	try:
		emailfrom = config["emailfrom"]
		to = config["emailto"]
		server = config["emailserver"]
		port = int(config["emailport"])
		smtpserver = smtplib.SMTP(server, port)
		smtpserver.ehlo()
		header = 'To: ' + to + '\nFrom: ' + emailfrom + '\nSubject: ' + subject + '\n'
		msg = header + '\n' + body + ' \n\n'
		smtpserver.sendmail(emailfrom, to, msg)
		smtpserver.close()
	except smtplib.SMTPException:
		# couldn't send.
		pass	

initGPIO()

#daemon.daemonize("/var/run/access.pid")

retstr = ''
repeat_read_timeout = time.time()
repeat_read_count = 0
open_hours = False
proc = subprocess.Popen(['/root/ac/wiegand'],stdout=subprocess.PIPE)
try:
	for line in iter(proc.stdout.readline, ''):
		ret = decodeStr(line)
		if (ret == -1):
			#print("Received an invalid or corrupted line")
			continue
	
		last_id = retstr
		retstr = str(ret)
		if (users.get(retstr) is None):
			subject = "Card " + retstr + " presented and access was denied."
			body = ""
			send_email(subject, body)
			continue
		now = time.time()
		if (retstr == last_id and now <= repeat_read_timeout):
			repeat_read_count += 1
		else:
			repeat_read_count = 0
			repeat_read_timeout = now + 120
		if (zone != "locker"):
			if (users[retstr][zone] == "Yes"):
				if (repeat_read_count >= 3):
					open_hours = True
					repeat_read_count = 0
					send_email("DOOR IS LOCKED OPEN", "")
				else:
					if (open_hours == True):
						send_email("DOOR IS NORMAL", "")
					open_hours = False
				triggerRelay(config[zone]["Relay"], open_hours)
				name = users[retstr].get("Name")
				first, last = name.split(" ");
				lastinitial = last[0];
				subject = first + " " + lastinitial + ". has entered zone " + zone
				body = ""
				send_email(subject, body)
			else:
				subject = "Card " + retstr + " presented and access was denied."
				body = ""
				send_email(subject, body)
		else:
			if (users[retstr].get("locker") is None):
				continue
			userlocker = users[retstr]["locker"]
			if (locker[userlocker]["Zone"] == lockerzone):
				triggerRelay(locker[userlocker]["Relay"])
except Exception as inst:
	print inst
	proc.terminate()

GPIO.cleanup()

