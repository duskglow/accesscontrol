#!/bin/bash

PID=`pidof python`
if [ -z $PID ]; then
	cd /root/ac/
	python access.py
fi

