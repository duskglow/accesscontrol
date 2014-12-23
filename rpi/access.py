import daemon
import RPi.GPIO as GPIO
import sys,time
import subprocess

import json

json_config = open("/root/ac/conf/config.json");
config = json.load(json_config);
json_config.close();

zone = config["zone"];

json_users = open("/root/ac/conf/users.json");
users = json.load(json_users);
json_users.close();

GPIO.setmode(GPIO.BCM)

relay = 4

GPIO.setup(relay, GPIO.OUT)

def triggerRelay():
	GPIO.output(relay, True);
	time.sleep(0.1);
	GPIO.output(relay, False);
	time.sleep(5);

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

daemon.daemonize("/var/run/access.pid")

proc = subprocess.Popen(['/root/ac/wiegand'],stdout=subprocess.PIPE)
try:
	for line in iter(proc.stdout.readline, ''):
		ret = decodeStr(line)
		if (ret == -1):
			#print("Received an invalid or corrupted line")
			continue
	
		retstr = str(ret)
		if (users.get(retstr) is None):
			continue
		if (users[retstr][zone] == "Yes"):
			triggerRelay()
except:
	proc.terminate()

GPIO.cleanup()

