#!/usr/bin/python
#
# vim: et ai sw=4

import RPi.GPIO as GPIO
import sys,time
import signal
import subprocess
import json
import smtplib
import threading
import syslog

debug_mode = False
conf_dir = "./conf/"
GPIO.setmode(GPIO.BCM)
syslog.openlog("accesscontrol", syslog.LOG_PID, syslog.LOG_AUTH)
syslog.syslog("Initializing")

# Globalize some variables for later
zone = None
users = None
config = None
active = None
locker = None
lockerzone = None
open_hours = False

def load_json(filename):
    file_handle = open(filename)
    config = json.load(file_handle)
    file_handle.close()
    return config

def read_configs():
    global zone, users, config, locker, lockerzone, active
    jzone = load_json(conf_dir + "zone.json")
    users = load_json(conf_dir + "users.json")
    config = load_json(conf_dir + "config.json")
    locker = load_json(conf_dir + "locker.json")
    zone = jzone["zone"]
    lockerzone = jzone["lockerzone"]
    active = config[zone]["Active"]

def init_GPIO(gpio):
    GPIO.setup(gpio, GPIO.OUT)
    GPIO.output(gpio, active^1)

def setup_GPIOs():
    if (zone == "locker"):
        for number in iter(locker):
            init_GPIO(locker[number]["Relay"])
    else:
        init_GPIO(config[zone]["Relay"])

def rehash(a=None, b=None):
    report("Reloading configuration files")
    read_configs()
    setup_GPIOs()

def triggerRelay(gpio_number, leave_open=False):
    gpio_number = gpio_number
    GPIO.output(gpio_number, active)
    if leave_open:
        return True
    time.sleep(config[zone]["open_delay"])
    GPIO.output(gpio_number, active^1)

def debug(message):
    if debug_mode:
        print message

def decodeStr(line):
    tbstr = line.split(" : ")[1]
    tbstr = tbstr.rstrip()
    bstr = tbstr[0:24] + tbstr[30:]

    if len(bstr) != 26:
        debug("Incorrect string length received: %i" % len(bstr))
        debug(":%s:" % bstr)
        return -1
    lparity = int(bstr[0])
    facility = int(bstr[1:9], 2)
    user_id = int(bstr[9:25], 2)
    rparity = int(bstr[25])
    lpstr = bstr[1:13]
    rpstr = bstr[13:25]

    debug(line.rstrip())
    debug("%i %i %i %i" % (lparity, facility, user_id, rparity))
    # check parity
    calculated_lparity = 0
    calculated_rparity = 1
    for iter in range(0, 12):
        calculated_lparity ^= int(lpstr[iter])
        calculated_rparity ^= int(rpstr[iter])
    if (calculated_lparity != lparity or calculated_rparity != rparity):
        debug("Parity error in received string!")
        return -1

    user_id = str(user_id)
    debug("Successfully decoded id %s" % user_id)
    return user_id

def send_email(subject, body=""):
    try:
        emailfrom = config["emailfrom"]
        to = config["emailto"]
        smtpserver = smtplib.SMTP(config["emailserver"], config["emailport"])
        smtpserver.ehlo()
        header = "To: %s\nFrom: %s\nSubject: %s\n" % (to, emailfrom, subject)
        msg = "%s\n%s\n\n" % (header, body)
        smtpserver.sendmail(emailfrom, to, msg)
        smtpserver.close()
    except smtplib.SMTPException:
        # couldn't send.
        pass

def report(subject):
    syslog.syslog(subject)
    if config and config.get("emailserver"):
        t = threading.Thread(target=send_email, args=(subject,))
        t.start()

def process_wiegand_line(line):
    global card_id, repeat_read_timeout, repeat_read_count, open_hours

    last_id = card_id
    card_id = decodeStr(line)
    if (card_id == -1):
        debug("Received an invalid or corrupted line")
        return
    if (users.get(card_id) is None):
        report("Card %s presented at %s and access was denied" % (card_id, zone))
        return

    now = time.time()
    if (card_id == last_id and now <= repeat_read_timeout):
        repeat_read_count += 1
    else:
        repeat_read_count = 0
        repeat_read_timeout = now + 120
    if (zone != "locker"):
        if (users[card_id][zone] == "Yes"):
            if (repeat_read_count >= 3):
                open_hours = True
                repeat_read_count = 0
                report("%s is unlocked" % zone)
            else:
                if (open_hours == True):
                    report("%s is locked" % zone)
                open_hours = False
            triggerRelay(config[zone]["Relay"], open_hours)
            first, last = users[card_id]["Name"].split(" ")
            report("%s %s. has entered %s" % (first, last[0], zone))
        else:
            report("A card was presented at %s and access was denied" % zone)
    else:
        if (users[card_id]["locker"] is None):
            return
        userlocker = users[card_id]["locker"]
        if (locker[userlocker]["Zone"] == lockerzone):
            triggerRelay(locker[userlocker]["Relay"])

def cleanup(a=None, b=None):
    report("Shutting down")
    GPIO.setwarnings(False)
    GPIO.cleanup()
    proc.terminate()
    sys.exit(0)

# Catch some exit signals
signal.signal(signal.SIGINT, cleanup)   # Ctrl-C
signal.signal(signal.SIGTERM, cleanup)  # killall python

# Reload config files
signal.signal(signal.SIGHUP, rehash)    # killall -HUP python
signal.signal(signal.SIGUSR2, rehash)   # killall -USR2 python

rehash()
card_id = ""
repeat_read_timeout = time.time()
repeat_read_count = 0
while True:
    proc = subprocess.Popen(["./wiegand"],stdout=subprocess.PIPE)
    try:
        for line in iter(proc.stdout.readline, ""):
            process_wiegand_line(line)
    except Exception as inst:
        print inst
        proc.terminate()

cleanup()
