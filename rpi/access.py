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

debug_mode = True
conf_dir = "./conf/"

def initialize():
    GPIO.setmode(GPIO.BCM)
    syslog.openlog("accesscontrol", syslog.LOG_PID, syslog.LOG_AUTH)
    report("Initializing")
    read_configs()
    setup_output_GPIOs()
    setup_readers()
    # Catch some exit signals
    signal.signal(signal.SIGINT, cleanup)   # Ctrl-C
    signal.signal(signal.SIGTERM, cleanup)  # killall python
    # These signals will reload users
    signal.signal(signal.SIGHUP, rehash)    # killall -HUP python
    signal.signal(signal.SIGUSR2, rehash)   # killall -USR2 python
    report("%s access control is online" % zone)

def report(subject):
    syslog.syslog(subject)
    debug(subject)
    if config and config.get("emailserver"):
        t = threading.Thread(target=send_email, args=(subject))
        t.start()

def debug(message):
    if debug_mode:
        print message

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

def rehash(signal=None, b=None):
    global users
    report("Reloading access list")
    users = load_json(conf_dir + "users.json")

def read_configs():
    global zone, users, config, locker, lockerzone
    jzone = load_json(conf_dir + "zone.json")
    users = load_json(conf_dir + "users.json")
    config = load_json(conf_dir + "config.json")
    zone = jzone["zone"]
    if zone == "locker":
        lockerzone = jzone["lockerzone"]
        locker = load_json(conf_dir + "locker.json")

def load_json(filename):
    file_handle = open(filename)
    config = json.load(file_handle)
    file_handle.close()
    return config

def setup_output_GPIOs():
    if (zone == "locker"):
        for number in iter(locker):
            gpio = locker[number]["latch_gpio"]
            zone_by_pin[gpio] = "locker"
            init_GPIO(gpio)
    else:
        zone_by_pin[config[zone]["latch_gpio"]] = zone
        init_GPIO(config[zone]["latch_gpio"])

def init_GPIO(gpio):
    GPIO.setup(gpio, GPIO.OUT)
    lock(gpio)

def lock(gpio):
    GPIO.output(gpio, active(gpio)^1)

def unlock(gpio):
    GPIO.output(gpio, active(gpio))

def active(gpio):
    zone = zone_by_pin[gpio]
    return config[zone]["unlock_value"]

def unlock_briefly(gpio):
    unlock(gpio)
    time.sleep(config[zone]["open_delay"])
    lock(gpio)

def setup_readers():
    global zone_by_pin
    for name in iter(config):
        if (type(config[name]) is dict and config[name].get("d0")
                                       and config[name].get("d1")):
            reader = config[name]
            reader["stream"] = ""
            reader["timer"] = None
            reader["name"] = name
            reader["unlocked"] = False
            zone_by_pin[reader["d0"]] = name
            zone_by_pin[reader["d1"]] = name
            GPIO.setup(reader["d0"], GPIO.IN)
            GPIO.setup(reader["d1"], GPIO.IN)
            GPIO.add_event_detect(reader["d0"], GPIO.FALLING,
                                  callback=data_pulse)
            GPIO.add_event_detect(reader["d1"], GPIO.FALLING,
                                  callback=data_pulse)

def data_pulse(channel):
    reader = config[zone_by_pin[channel]]
    if channel == reader["d0"]:
        reader["stream"] += "0"
    elif channel == reader["d1"]:
        reader["stream"] += "1"
    kick_timer(reader)

def kick_timer(reader):
    if reader["timer"] is None:
        reader["timer"] = threading.Timer(0.2, wiegand_stream_done,
                                          args=[reader])
        reader["timer"].start()

def wiegand_stream_done(reader):
    if reader["stream"] == "":
        return
    bitstring = reader["stream"]
    reader["stream"] = ""
    reader["timer"] = None
    validate_bits(bitstring)

def validate_bits(bstr):
    if len(bstr) != 26:
        debug("Incorrect string length received: %i" % len(bstr))
        debug(":%s:" % bstr)
        return False
    lparity = int(bstr[0])
    facility = int(bstr[1:9], 2)
    user_id = int(bstr[9:25], 2)
    rparity = int(bstr[25])
    debug("%s is: %i %i %i %i" % (bstr, lparity, facility, user_id, rparity))

    calculated_lparity = 0
    calculated_rparity = 1
    for iter in range(0, 12):
        calculated_lparity ^= int(bstr[iter+1])
        calculated_rparity ^= int(bstr[iter+13])
    if (calculated_lparity != lparity or calculated_rparity != rparity):
        debug("Parity error in received string!")
        return False

    card_id = "%08x" % int(bstr, 2)
    debug("Successfully decoded %s facility=%i user=%i" %
          (card_id, facility, user_id))
    lookup_card(card_id, str(facility), str(user_id))

def lookup_card(card_id, facility, user_id):
    user = (users.get("%s,%s" % (facility, user_id)) or
            users.get(card_id) or
            users.get(user_id))
    if (user is None):
        debug("couldn't find user")
        return reject_card()
    if (zone == "locker" and user.get("locker")):
        open_locker(user)
    elif (user.get(zone) and user[zone] == "Yes"):
        open_door(user)
    else:
        debug("user isn't authorized for this zone")
        reject_card()

def reject_card():
    report("A card was presented at %s and access was denied" % zone)
    return False

def open_locker(user):
    userlocker = user["locker"]
    if locker.get(userlocker) is None:
        return debug("%s's locker does not exist" % user["name"])
    if (locker[userlocker]["zone"] == lockerzone):
        report("%s has opened their locker" % public_name(user))
        unlock_briefly(locker[userlocker]["latch_gpio"])

def public_name(user):
    first, last = user["name"].split(" ")
    return "%s %s." % (first, last[0])

def open_door(user):
    global open_hours, last_name, repeat_read_timeout, repeat_read_count
    now = time.time()
    name = public_name(user)
    if (name == last_name and now <= repeat_read_timeout):
        repeat_read_count += 1
    else:
        repeat_read_count = 0
        repeat_read_timeout = now + 30
    last_name = name
    if (repeat_read_count >= 2):
        config[zone]["unlocked"] ^= True
        if config[zone]["unlocked"]:
            unlock(config[zone]["latch_gpio"])
            report("%s unlocked by %s" % (zone, name))
        else:
            lock(config[zone]["latch_gpio"])
            report("%s locked by %s" % (zone, name))
    else:
        if config[zone]["unlocked"]:
            report("%s found %s is already unlocked" % (name, zone))
        else:
            unlock_briefly(config[zone]["latch_gpio"])
            report("%s has entered %s" % (name, zone))

def cleanup(a=None, b=None):
    message = ""
    if zone:
        message = "%s " % zone
    message += "access control is going offline"
    report(message)
    GPIO.setwarnings(False)
    GPIO.cleanup()
    sys.exit(0)

# Globalize some variables for later
zone = None
users = None
config = None
locker = None
last_name = None
lockerzone = None
zone_by_pin = {}
repeat_read_count = 0
repeat_read_timeout = time.time()

initialize()
while True:
    # The main thread should open a command socket or something
    time.sleep(1000)
