# WPSD-SeenGreat-UPS-Monitor
Script for Raspberry PI UPS from SeenGreat, to monitor and shut the pi down when battery falls below 20%

This script at this time is specifically written for the WPSD hotspot usage as it will write the the status to the OLED screen on the hotspot when the system is detected as running on battery.
To get started I forked the repository from seengreat here:  https://github.com/seengreat/Pi-Zero-UPS-USB-HUB

I also made modifications to allow it to run on a pistar hotspot that uses the Seengreat UPS pi hat as well.  Specific to Pi-Star the steps would be as follows.

SSH to the pi-star system and run the following

rpi-rw

git clone --branch Beta --single-branch -depth 1 https://github.com/TheSystech/WPSD-SeenGreat-UPS-Monitor.git

cd WPSD-SeenGreat-UPS-Monitor

chmod +x install.sh

sudo ./install.sh



You can either manually follow the steps in install.sh, or you can chmod +x on install.sh and run it with SUDO after cloning to the system.
