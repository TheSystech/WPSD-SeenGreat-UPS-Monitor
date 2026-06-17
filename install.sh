#!/bin/bash
# Make directory 
mkdir /opt/UPS
#Copy the python files to the directory
cp *.py /opt/UPS
#Check to see if smbus python module is available
output=$(dpkg -l |grep python3-smbus)
if [[ "$output" == *"SMBus"* ]]; then
  echo "SMBus was already installed"
else
  #Install the smbus python3 module.
  apt -y install python3-smbus
fi
#copy the systemd file to the correct location
cp ups-monitor.service /etc/systemd/system/
cp ups_monitor.conf /etc/
#Activate the new service on boot and start it now.
systemctl enable ups-monitor
systemctl start ups-monitor
