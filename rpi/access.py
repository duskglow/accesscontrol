#!/usr/bin/python
#import daemon	# This is not used anymore
import RPi.GPIO as GPIO
import sys,time
import signal
import subprocess

import json
import smtplib

conf_dir = './conf/'

GPIO.setmode(GPIO.BCM)

zone = None
users = None
config = None
locker = None
active = None

def read_configs():
	json_zone = open(conf_dir + 'zone.json');
	jzone = json.load(json_zone);
	json_zone.close();

	global zone 
	zone = jzone["zone"];

	global users
	json_users = open(conf_dir + 'users.json');
	users = json.load(json_users);
	json_users.close();

	global config
	json_config = open(conf_dir + 'config.json');
	config = json.load(json_config);
	json_config.close();

	global locker
	json_locker = open(conf_dir + 'locker.json');
	locker = json.load(json_locker);
	json_locker.close();

	if (zone == "locker"):
		lockerzone = jzone["lockerzone"]

	# initialize some variables, should do this in a def.
	global active
	active = config[zone]["Active"]
	if active == 'High':
		active = GPIO.HIGH
	elif active == 'Low':
		active = GPIO.LOW
	else:
		print ("Invalid active directive for zone " + zone)
		sys.exit(0)

def initGPIO():
	if (zone == "locker"):
		for relay in iter(locker):
			r = int(locker[relay]["Relay"])
			GPIO.setup(r, GPIO.OUT)
			GPIO.output(r, True)
	else :
		r = int(config[zone]["Relay"])
		GPIO.setup(r, GPIO.OUT)
		GPIO.output(r, active^1)

def rehash(a=None, b=None):
	read_configs()
	initGPIO()

def triggerRelay(r, open_hours=False):
	relay = int(r)
	if (zone == "locker"):
		GPIO.output(relay, False)
		time.sleep(2)
		GPIO.output(relay, True)
	else:
		GPIO.output(relay, active)
		if (open_hours):
			return True
		time.sleep(0.1)
		GPIO.output(relay, active^1)

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

def process_line(line):
	global retstr
	global repeat_read_timeout
	global repeat_read_count
	global open_hours

	ret = decodeStr(line)
	if (ret == -1):
		#print("Received an invalid or corrupted line")
		return 1

	last_id = retstr
	retstr = str(ret)
	if (users.get(retstr) is None):
		subject = "Card " + retstr + " presented and access was denied."
		body = ""
		send_email(subject, body)
		return 1
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
			return 1
		userlocker = users[retstr]["locker"]
		if (locker[userlocker]["Zone"] == lockerzone):
			triggerRelay(locker[userlocker]["Relay"])

def cleanup(a=None, b=None):
	GPIO.setwarnings(False)
	GPIO.cleanup()
	proc.terminate()
	sys.exit(0)

rehash()
signal.signal(signal.SIGINT, cleanup)	# Ctrl-C will try to exit cleanly
signal.signal(signal.SIGTERM, cleanup)	# default kill signal (killall python)
signal.signal(signal.SIGHUP, rehash)	# reload config files (killall -HUP python)
signal.signal(signal.SIGUSR2, rehash)	# reload config files (killall -USR2 python)

#daemon.daemonize("/var/run/access.pid")

retstr = ''
repeat_read_timeout = time.time()
repeat_read_count = 0
open_hours = False
while (True):
	proc = subprocess.Popen(['./wiegand'],stdout=subprocess.PIPE)
	try:
		for line in iter(proc.stdout.readline, ''):
			process_line(line)
	except Exception as inst:
		print inst
		proc.terminate()

cleanup()
