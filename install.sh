#!/bin/bash
# Make directory 
mkdir /opt/UPS
#Copy the python files to the directory
cp *.py /opt/UPS
#Install the smbus python3 module.
apt install python3-smbus
#copy the systemd file to the correct location
cp ups-monitor.service /etc/systemd/system/
#Activate the new service on boot and start it now.
systemctl enable ups-monitor
systemctl start ups-monitor
